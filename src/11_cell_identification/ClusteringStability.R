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

tmp_parser <- arg_parser("Clustering Stability (Consensus).")

# Add command line arguments
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
                           arg = "--path.output.folder",
                           help = "Path to input csv where the results will be stored (directory).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

ClusteringStability <- function(input.phenograph, # Path to input csv where the phenograph data is stored (.csv).
                                input.kmeans, # Path to input csv where the kmeans data is stored (.csv).
                                input.flowsom, # Path to input csv where the flowsom data is stored (.csv).
                                annotation.dictionary, # Path to input csv where the annotations are stored (.csv).
                                output.folder # Path to output directory where the figures and html will be generated (dir).
){
  if(missing(input.phenograph)) {
    input.phenograph <- 'not included'
  }
  if(missing(input.kmeans)) {
    input.kmeans <- 'not included'
  }
  if(missing(input.flowsom)) {
    input.flowsom <- 'not included'
  }
  
  print(paste0('### input phenograph: ', input.phenograph, ' ###')) 
  print(paste0('### input kmeans: ', input.kmeans, ' ###')) 
  print(paste0('### input flowsom: ', input.flowsom, ' ###')) 
  print(paste0('### annotation dictionary: ', annotation.dictionary, ' ###')) 
  print(paste0('### output folder: ', output.folder, ' ###')) 

  if(!(dir.exists(output.folder))){
    print(paste('### creating folder: ', output.folder, ' ###'))
    dir.create(output.folder, recursive = TRUE)
  }
  
  # Load data file ------------------------------------------------------------------
  
  print('Loading data file')
  
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
  
  annotation_dictionary <- read.csv(annotation.dictionary, stringsAsFactors = FALSE) %>% 
    filter(annotated == 1)
  
  # Merge clusters and annotations ------------------------------------------------------------------
  
  print('Merging clusters and annotations')
  
  df_clusters <- df_clusters %>%
    left_join(annotation_dictionary) %>% 
    filter(annotated == 1) %>% 
    select(-cluster, -annotated) %>% 
    mutate(annotation = as.character(annotation))
  
  print(table(df_clusters[c('annotation', 'cl_method')]))
  
  # Generate Jaccard matrices ------------------------------------------------------------------
  
  print('Generating Jaccard matrices')
  
  df_jaccard <- data.frame()
  
  for(i in unique(df_clusters$cl_method)){
    for(j in unique(df_clusters$cl_method)){
      if(which(unique(df_clusters$cl_method) %in% i) >= which(unique(df_clusters$cl_method) %in% j)) next
      else{
        tmp_clusters <- df_clusters %>% 
          filter(cl_method %in% c(i, j)) %>% 
          mutate(cl_method = plyr::mapvalues(cl_method, from = c(i, j), to = c('X', 'Y'))) %>% 
          ungroup() %>% unique() %>% 
          spread(cl_method, annotation)
        
        tmp_plot <- data.frame()
        
        for(k in unique(df_clusters$annotation)){
          for(l in unique(df_clusters$annotation)){
            tmp_n <- nrow(filter(tmp_clusters, X == k, Y == l))
            tmp_jaccard <- nrow(filter(tmp_clusters, X == k, Y == l)) / nrow(filter(tmp_clusters, X == k | Y == l))
            if(is.nan(tmp_jaccard)) tmp_jaccard <- 0
            tmp_plot <- bind_rows(tmp_plot, data.frame(ClusterX = k, ClusterY = l, Jaccard = tmp_jaccard, N = tmp_n))
          }
        }
        
        tmp_clusterX <- tmp_clusters %>% 
          rename(ClusterX = X) %>% 
          group_by(ClusterX) %>% 
          summarise(N = n()) %>% 
          ungroup() %>% 
          mutate(Jaccard = 0, ClusterY = 'Total', ClusterX = as.character(ClusterX))
        
        tmp_clusterY <- tmp_clusters %>% 
          rename(ClusterY = Y) %>% 
          group_by(ClusterY) %>% 
          summarise(N = n()) %>% 
          ungroup() %>% 
          mutate(Jaccard = 0, ClusterX = 'Total', ClusterY = as.character(ClusterY))
        
        tmp_plot <- tmp_plot %>% 
          bind_rows(tmp_clusterX) %>% 
          bind_rows(tmp_clusterY) %>% 
          mutate(ClusterX = factor(ClusterX, levels = c(setdiff(unique(ClusterX), 'Total'), 'Total')), 
                 ClusterY = factor(ClusterY, levels = rev(c(setdiff(unique(ClusterX), 'Total'), 'Total')))) 
        
        tmp_p1 <- ggplot(tmp_plot, aes(ClusterX, ClusterY, fill = Jaccard)) +
          geom_tile(color = "gray", size = 0.1) +
          geom_text(data = tmp_plot, aes(ClusterX, ClusterY, label = round(N, 0))) +
          scale_fill_gradient(low = 'white', high = 'firebrick') +
          #coord_equal() +
          labs(x = i, y = j, title = paste0('Cluster Intersection: ', i, ' vs ', j)) +
          theme_bw() +
          theme(axis.text.x = element_text(angle = 90, hjust = 1)) +
          theme(axis.ticks = element_blank(), plot.title = element_text(hjust = 0.5))
        
        png(file.path(output.folder, paste0('jaccard_matrix_', i, '_', j, '.png')), width = n_distinct(tmp_plot$ClusterX)/2, height = n_distinct(tmp_plot$ClusterY)/2, units = 'in', res = 300)
        print(tmp_p1)
        dev.off()
        
        for(tmp_cluster in setdiff(unique(tmp_plot$ClusterX), c('Total', NA))){
          tmp_j <- tmp_plot %>% filter(ClusterX == tmp_cluster) %>% filter(Jaccard == max(Jaccard)) %>% sample_n(1)
          if(tmp_j$J == 0) next
          df_jaccard <- df_jaccard %>% bind_rows(data.frame(ClusterX = i, ClusterY = j, Cluster = tmp_cluster, J = tmp_j$J))
        }
        
        for(tmp_cluster in setdiff(unique(tmp_plot$ClusterY), c('Total', NA))){
          tmp_j <- tmp_plot %>% filter(ClusterY == tmp_cluster) %>% filter(Jaccard == max(Jaccard)) %>% sample_n(1)
          if(tmp_j$J == 0) next
          df_jaccard <- df_jaccard %>% bind_rows(data.frame(ClusterY = i, ClusterX = j, Cluster = tmp_cluster, J = tmp_j$J))
        }
      }
    }
  }
  

  # Naming consensus ------------------------------------------------------------------
  
  print('Naming consensus')
  
  unique_methods <- unique(df_clusters$cl_method)
  
  wide_df <- df_clusters %>%
    pivot_wider(names_from = cl_method, values_from = annotation)
  
  grouping_vars <- syms(unique_methods) # Convert unique methods to symbols for dynamic evaluation
  
  tmp_clusters <- wide_df %>% 
    group_by(!!!grouping_vars) %>% # The !!! operator is used to splice a list of symbols or expressions into a function call
    summarise(N = n(), .groups = 'drop')
  
  df_agreements <- data.frame()
  df_noise <- data.frame()
  
  for (i in 1:nrow(tmp_clusters)) {
    tmp_group <- tmp_clusters[i, ]
    
    # Transform to long format and split names
    tmp_name <- tmp_group %>%
      pivot_longer(cols = -N, names_to = "CM", values_to = "Name") %>%
      mutate(Name = str_split(Name, pattern = "_", simplify = TRUE)[, 1])
    
    # Count the frequency of each name
    name_freq <- tmp_name %>%
      count(Name) %>%
      rename(Freq = n) %>% 
      mutate(N = length(unique_methods)) %>% 
      mutate(P = Freq/N) %>% 
      filter(P == max(P)) %>% 
      filter(P > 0.5)
    
    if(nrow(name_freq) == 1){
      df_agreements <- df_agreements %>% bind_rows(tmp_group %>% mutate(CellType = name_freq$Name))
    } else {
      df_noise <- df_noise %>% bind_rows(tmp_group %>% mutate(CellType = 'NOISE'))
    }
  }
  
  print('Agreement')
  print(sum(df_agreements$N))

  print('Inconsistent')
  print(sum(df_noise$N))
  
  # Map names ------------------------------------------------------------------
  
  print('Mapping names')
  
  df_clusters_annotated <- wide_df %>% 
    left_join(df_agreements) %>% 
    filter(!is.na(CellType)) %>% 
    select(slide_id, scene_id, OID, CellType)
  
  write.csv(df_clusters_annotated, file.path(output.folder, 'df_data_consensus.csv'), row.names = FALSE)
  write.csv(df_clusters_annotated %>% select(CellType) %>% unique(), file.path(output.folder, 'df_consensus_celltypes.csv'), row.names = FALSE)
}


# Parser check -------------------------------------------------------------------
required_args <- c("path.annotation.dictionary", "path.output.folder")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
ClusteringStability(input.phenograph = argv$path.input.phenograph, # Path to input csv with PhenoGraph data (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/phenograph.csv
                    input.kmeans = argv$path.input.kmeans, # Path to input csv with KMeans data (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/kmeans.csv
                    input.flowsom = argv$path.input.flowsom, # Path to input csv with FlowSom data (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/flowsom.csv
                    annotation.dictionary = argv$path.annotation.dictionary, # Path to input csv where the annotations are stored (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/annotation_dictionary.csv
                    output.folder = argv$path.output.folder # Path to output folder where the results from the clustering will be stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01
)
