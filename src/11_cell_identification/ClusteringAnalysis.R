#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

### sudo apt install liblapack-dev libopenblas-dev
### sudo apt-get install gfortran
list.of.packages <- c('RSpectra', 'RcppEigen', "tidyverse", "EBImage", "argparser", 'doSNOW', 'readxl', 'pastecs', 'graphics', 'pbapply', 'parallel', 'reticulate', 'RColorBrewer',
                      'corrplot', 'devtools', 'igraph')
new.packages <- list.of.packages[!(list.of.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)) install.packages(new.packages, repos = "http://cran.us.r-project.org")

list.of.bioconductor.packages <- c('EBImage')
new.packages <- list.of.bioconductor.packages[!(list.of.bioconductor.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)){
  if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager")
  BiocManager::install(new.packages)
}

library(tidyverse)
library(pbapply)
library(EBImage)  
library(doSNOW)
library(reticulate)
library(RColorBrewer)
library(corrplot)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Clustering.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input.marker.list",
                           help = "List of markers (csv)",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv",
                           help = "Path to input csv where the sampled data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.pca",
                           help = "Path to input csv where the PCA data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.tsne",
                           help = "Path to input csv where the tsne data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.umap",
                           help = "Path to input csv where the uMap data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.phenograph",
                           help = "Path to input csv where the phenograph data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.kmeans",
                           help = "Path to input csv where the kmeans data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.flowsom",
                           help = "Path to input csv where the flowsom data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.annotation.dictionary",
                           help = "Path to input csv where the annotations are stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--generate.marker.plots",
                           help = "Argument to generate marker plots or not (binary).",
                           type = "numeric")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to input csv where the results will be stored (directory).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

ClusteringAnalysis <- function(marker.list, # Path to input exp design for the rounds (.csv).
                               input.csv, # Path to input csv with sampled cells (.csv).
                               input.pca, # Path to input csv where the pca data is stored (.csv).
                               input.tsne, # Path to input csv where the tsne data is stored (.csv).
                               input.umap, # Path to input csv where the umap data is stored (.csv).
                               input.phenograph, # Path to input csv where the phenograph data is stored (.csv).
                               input.kmeans, # Path to input csv where the kmeans data is stored (.csv).
                               input.flowsom, # Path to input csv where the flowsom data is stored (.csv).
                               annotation.dictionary, # Path to input csv where the annotations are stored (.csv).
                               marker.plots, # Argument to generate marker plots or not (binary).
                               output.folder # Path to output directory where the figures and html will be generated (dir).
){
  if(missing(input.pca)) {
    input.pca <- 'not included'
  }
  if(missing(input.tsne)) {
    input.tsne <- 'not included'
  }
  if(missing(input.umap)) {
    input.umap <- 'not included'
  }
  if(missing(input.phenograph)) {
    input.phenograph <- 'not included'
  }
  if(missing(input.kmeans)) {
    input.kmeans <- 'not included'
  }
  if(missing(input.flowsom)) {
    input.flowsom <- 'not included'
  }
  if(missing(annotation.dictionary)) {
    annotation.dictionary <- 'not included'
  }
  print(paste0('### list of markers: ', marker.list, ' ###')) 
  print(paste0('### input csv: ', input.csv, ' ###')) 
  print(paste0('### input pca: ', input.pca, ' ###')) 
  print(paste0('### input tsne: ', input.tsne, ' ###')) 
  print(paste0('### input umap: ', input.umap, ' ###')) 
  print(paste0('### input phenograph: ', input.phenograph, ' ###')) 
  print(paste0('### input kmeans: ', input.kmeans, ' ###')) 
  print(paste0('### input flowsom: ', input.flowsom, ' ###')) 
  print(paste0('### annotation dictionary: ', annotation.dictionary, ' ###')) 
  print(paste0('### marker plots: ', marker.plots, ' ###')) 
  print(paste0('### output folder: ', output.folder, ' ###')) 

  if(!(dir.exists(output.folder))){
    print(paste('### creating folder: ', output.folder, ' ###'))
    dir.create(output.folder, recursive = TRUE)
  }
  
  marker.plots <- as.integer(marker.plots)
  range.x1_q <- function(x, q){
    tmp_q_high <- quantile(x, q)
    tmp_q_low <- quantile(x, 1-q)
    
    if(tmp_q_high == tmp_q_low){
      x <- x/max(x)
    } else {
      x <- (x-tmp_q_low)/(tmp_q_high-tmp_q_low)
    }
    x[x>1] <- 1
    x[x<0] <- 0
    return(x)
  }
  
  range01 <- function(x){(x-min(x))/(max(x)-min(x))}
  
  # Load exp design files ------------------------------------------------------------------
  
  print('Loading list of markers')
  
  phenotypic_markers <- read.csv(marker.list, stringsAsFactors = FALSE) %>% mutate(marker_id = toupper(marker_id)) %>%
    mutate(marker_id = toupper(gsub('-', '.', marker_id)))
  
  print(phenotypic_markers$marker_id)
  
  # Load data file ------------------------------------------------------------------
  
  print('Loading data file')
  
  df_data <- read.csv(input.csv, stringsAsFactors = FALSE, check.names = FALSE)
  colnames(df_data) <- lapply(colnames(df_data), function(x) toupper(gsub('-', '.', x)))
  
  df_data <- df_data[complete.cases(df_data),]
  df_data <- df_data %>% rename(s.area = S.AREA, slide_id = SLIDE_ID, scene_id = SCENE_ID)
  
  tmp_wrong_names <- setdiff(phenotypic_markers$marker_id, colnames(df_data))
  if(length(tmp_wrong_names) > 0){
    print(paste(tmp_wrong_names, 'not found, it will not be included in the clustering.'))
    phenotypic_markers <- phenotypic_markers %>% filter(marker_id %in% colnames(df_data))
  }
  
  df_data <- df_data %>% select(OID:scene_id, phenotypic_markers$marker_id) %>% gather(marker, value, phenotypic_markers$marker_id)
  
  df_dr <- data.frame()
  if(input.pca != 'not included'){
    tmp_pca <- read.csv(input.pca, stringsAsFactors = FALSE)
    df_dr <- df_dr %>% bind_rows(tmp_pca)
  }
  
  if(input.tsne != 'not included'){
    tmp_tsne <- read.csv(input.tsne, stringsAsFactors = FALSE)
    df_dr <- df_dr %>% bind_rows(tmp_tsne)
  }
  
  if(input.umap != 'not included'){
    tmp_umap <- read.csv(input.umap, stringsAsFactors = FALSE)
    df_dr <- df_dr %>% bind_rows(tmp_umap)
  }
  
  df_clusters <- data.frame()
  if(input.flowsom != 'not included'){
    tmp_flowsom <- read.csv(input.flowsom, stringsAsFactors = FALSE)
    df_clusters <- df_clusters %>% bind_rows(tmp_flowsom)
  }
  
  if(input.kmeans != 'not included'){
    tmp_kmeans <- read.csv(input.kmeans, stringsAsFactors = FALSE)
    df_clusters <- df_clusters %>% bind_rows(tmp_kmeans)
  }
  
  if(input.phenograph != 'not included'){
    tmp_phenograph <- read.csv(input.phenograph, stringsAsFactors = FALSE)
    df_clusters <- df_clusters %>% bind_rows(tmp_phenograph)
  }
  
  # Map dictionary ------------------------------------------------------------------
  
  print('Mapping annotation dictionary')
  
  if(annotation.dictionary != 'not included'){
    annotation_dictionary <- try(read.csv(annotation.dictionary, stringsAsFactors = FALSE))
  } else {
    annotation_dictionary <- df_clusters %>% select(cl_method, cluster) %>% unique() %>% mutate(annotation = cluster)
    write.csv(annotation_dictionary, file.path(output.folder, 'annotation_dictionary.csv'), row.names = FALSE)
  }
  
  if(class(annotation_dictionary) == 'try-error'){
    annotation_dictionary <- df_clusters %>% select(cl_method, cluster) %>% unique() %>% mutate(annotation = cluster)
    write.csv(annotation_dictionary, annotation.dictionary, row.names = FALSE)
  }
  
  # Generating DR plots ------------------------------------------------------------------
  
  print('Generating DR plots')
  
  df_clusters <- df_clusters %>%
    left_join(annotation_dictionary) %>% 
    select(-cluster) %>% 
    rename(cluster = annotation) %>% 
    mutate(cluster = as.character(cluster))
  
  tmp_plot <- df_clusters %>%
    left_join(df_dr)
  
  tmp_centroids <- tmp_plot %>% 
    group_by(cl_method, dr_method, cluster) %>% 
    summarise(X = median(X), Y = median(Y)) %>% 
    ungroup()
  
  for(tmp_dr in unique(tmp_plot$dr_method)){
    for(tmp_cl in unique(tmp_plot$cl_method)){
      png(file.path(output.folder, paste0('dr_clusters_', tmp_dr, '_', tmp_cl, '.png')), width = 4, height = 4, units = 'in', res = 300)
      print(ggplot(tmp_plot %>% filter(dr_method == tmp_dr, cl_method == tmp_cl), aes(X, Y, color = cluster)) + 
              geom_point() + 
              theme_bw() + 
              geom_label(data = tmp_centroids %>% filter(dr_method == tmp_dr, cl_method == tmp_cl), aes(X, Y, color = cluster, label = cluster)) +
              theme(legend.position = 'none'))
      dev.off()
    }
  }
  
  if(input.umap != 'not included'){
    png(file.path(output.folder, 'dr_clusters_umap.png'), width = n_distinct(tmp_plot$cl_method)*4, height = 4, units = 'in', res = 300)
    print(ggplot(tmp_plot %>% filter(dr_method == 'uMap'), aes(X, Y, color = cluster)) + 
            geom_point() + 
            theme_bw() + 
            facet_wrap(~cl_method) + 
            geom_label(data = tmp_centroids %>% filter(dr_method == 'uMap'), aes(X, Y, color = cluster, label = cluster)) +
            theme(legend.position = 'none'))
    dev.off()
  }
  
  if(marker.plots == TRUE){
    tmp_plot <- df_data %>%
      select(-X, -Y) %>%
      left_join(df_dr) 
    
    png(file.path(output.folder, 'clustering_PCA_markers.png'), width = 16, height = 2*ceiling(n_distinct(phenotypic_markers$marker_id)/8), units = 'in', res = 300)
    print(ggplot(tmp_plot %>% filter(dr_method == 'PCA'), aes(X, Y, color = value)) + 
            geom_point() + 
            theme_bw() + 
            facet_wrap(~marker, nrow = ceiling(n_distinct(phenotypic_markers$marker_id)/8)) + 
            scale_color_gradient2(low = 'royalblue', mid = 'white', high = 'firebrick', midpoint = 0)) #viridis::scale_color_viridis()
    dev.off()
    
    png(file.path(output.folder, 'clustering_uMap_markers.png'), width = 16, height = 2*ceiling(n_distinct(phenotypic_markers$marker_id)/8), units = 'in', res = 300)
    print(ggplot(tmp_plot %>% filter(dr_method == 'uMap'), aes(X, Y, color = value)) + 
            geom_point() + 
            theme_bw() + 
            facet_wrap(~marker, nrow = ceiling(n_distinct(phenotypic_markers$marker_id)/8)) + 
            scale_color_gradient2(low = 'royalblue', mid = 'white', high = 'firebrick', midpoint = 0)) #viridis::scale_color_viridis()
    dev.off()
    
    png(file.path(output.folder, 'clustering_tsne_markers.png'), width = 16, height = 2*ceiling(n_distinct(phenotypic_markers$marker_id)/8), units = 'in', res = 300)
    print(ggplot(tmp_plot %>% filter(dr_method == 'tsne'), aes(X, Y, color = value)) + 
            geom_point() + 
            theme_bw() + 
            facet_wrap(~marker, nrow = ceiling(n_distinct(phenotypic_markers$marker_id)/8)) + 
            scale_color_gradient2(low = 'royalblue', mid = 'white', high = 'firebrick', midpoint = 0)) #viridis::scale_color_viridis()
    dev.off()
  }
  
  # Evaluating cluster percentages ------------------------------------------------------------------
  
  print('Evaluating cluster percentages')
  
  percentages <- table(df_clusters[c('cluster', 'cl_method')]) %>%
    as.data.frame() %>%
    dplyr::rename(NCells = Freq) %>%
    group_by(cl_method) %>%
    mutate(Percentage = 100*(NCells/sum(NCells))) %>%
    ungroup() %>%
    select(-NCells) %>%
    arrange(cluster) %>% 
    mutate(cluster = factor(cluster, levels = unique(cluster)))
  
  # Generating heatmaps ------------------------------------------------------------------
  
  print('Generating heatmaps')
  
  df_heatmap <- df_data %>%
    left_join(df_clusters) %>% 
    select(marker, value, cl_method, cluster) %>%
    group_by(cl_method, cluster, marker) %>%
    summarise(M = mean(value)) %>%
    ungroup() %>% 
    mutate(cluster = factor(cluster, levels = unique(cluster)))

  hmcol <- rev(colorRampPalette(brewer.pal(9, "RdYlBu"))(100))

  for(i in unique(df_heatmap$cl_method)){
    tmp_heatmap <- df_heatmap %>%
      filter(cl_method == i) %>%
      droplevels()
    
    tmp_percentages <- percentages %>% 
      filter(cl_method == i) %>% 
      filter(Percentage > 0) %>% 
      droplevels()
    
    tmp_plot <- tmp_heatmap %>%
      group_by(cluster) %>%
      arrange(-M) %>%
      mutate(N = 1:n()) %>%
      ungroup() %>%
      filter(N <= 15)

    tmp_heatmap <- tmp_heatmap %>%
      spread(marker, M) %>%
      dplyr::select(-cl_method) %>%
      as.data.frame()
    rownames(tmp_heatmap) <- tmp_heatmap$cluster
    tmp_heatmap <- tmp_heatmap %>% select(-cluster) %>% as.matrix()
    
    tmp_p <- gplots::heatmap.2(tmp_heatmap, labCol = colnames(tmp_heatmap), trace = "none", key.title = 'R01 value', main = i, col = hmcol)

    tmp_plot <- tmp_plot %>%
      mutate(N = as.character(N)) %>%
      bind_rows(tmp_percentages %>%
                  filter(cl_method == i) %>% rename(M = Percentage) %>%
                  mutate(cluster = as.factor(cluster), marker = as.character(round(M, 2)), M = 0, N = as.factor('Percentages'))) %>%
      mutate(cluster = factor(cluster, levels = rownames(tmp_heatmap[tmp_p$rowInd,])), N = factor(N, levels = c(1:15, 'Percentages'))) %>%
      filter(marker != 0)
    
    png(file.path(output.folder, paste0(i, '_heatmap.png')), width = 10, height = round(nrow(tmp_heatmap)/3), units = 'in', res = 300)
    print(ggplot(tmp_plot, aes(N, cluster, fill = M)) +
            geom_tile(color = "white", size = 0.1) +
            geom_text(data = tmp_plot, aes(N, cluster, label = marker), size = 3) +
            scale_fill_gradient2(low = 'royalblue', midpoint = 0, mid = 'white', high = 'firebrick') +
            #coord_equal() +
            labs(x = NULL, y = NULL, title = paste0('Top 15 Expressed Markers per cluster (', i, ')')) +
            theme_bw() +
            theme(axis.ticks = element_blank(), plot.title = element_text(hjust = 0.5)))
    dev.off()
    
  }
}


# Parser check -------------------------------------------------------------------
required_args <- c("input.marker.list", "path.input.csv",  
                   "generate.marker.plots", "path.output.folder")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
ClusteringAnalysis(marker.list = argv$input.marker.list, # Path to input csv where the markers selected for the clustering are saved (.csv). Example: /path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv
                   input.csv = argv$path.input.csv, # Path to input csv with sampled data  (.csv).Example: /path/to/project_directory/output_cell_identification/n01/df_data_sampled.csv
                   input.pca = argv$path.input.pca, # Path to input csv with PCA data, if existing (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/pca.csv
                   input.tsne = argv$path.input.tsne, # Path to input csv with tSNE data, if existing (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/tsne.csv
                   input.umap = argv$path.input.umap, # Path to input csv with uMap data, if existing (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/uMap.csv
                   input.phenograph = argv$path.input.phenograph, # Path to input csv with PhenoGraph data (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/phenograph.csv
                   input.kmeans = argv$path.input.kmeans, # Path to input csv with KMeans data (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/kmeans.csv
                   input.flowsom = argv$path.input.flowsom, # Path to input csv with FlowSom data (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/flowsom.csv
                   annotation.dictionary = argv$path.annotation.dictionary, # Path to input csv where the annotations are stored (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/annotation_dictionary.csv
                   marker.plots = argv$generate.marker.plots, # Binary describing if marker plots need to be generated (binary). Example: 1
                   output.folder = argv$path.output.folder # Path to output folder where plots will be saved (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01
)