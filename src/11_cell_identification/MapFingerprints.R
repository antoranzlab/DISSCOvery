#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

### sudo apt install liblapack-dev libopenblas-dev
### sudo apt-get install gfortran
list.of.packages <- c('RSpectra', 'RcppEigen', "tidyverse", "EBImage", "argparser", 'doSNOW', 'readxl', 'pastecs', 'graphics', 'pbapply', 'parallel', 'doParallel', 'itertools', 'reticulate', 'RColorBrewer', 
                      'corrplot', 'umap', 'Rtsne', 'devtools', 'igraph', 'plotly', 'htmlwidgets')
new.packages <- list.of.packages[!(list.of.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)) install.packages(new.packages, repos = "http://cran.us.r-project.org")

list.of.bioconductor.packages <- c('EBImage', 'FlowSOM')
new.packages <- list.of.bioconductor.packages[!(list.of.bioconductor.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)){
  if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager")
  BiocManager::install(new.packages)
}

list.of.github.packages <- c('Rphenograph')
new.packages <- list.of.github.packages[!(list.of.github.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)){
  if(!require(devtools)){
    install.packages("devtools") # If not already installed
  }
  devtools::install_github("JinmiaoChenLab/Rphenograph")
} 

library(tidyverse)
library(umap)
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
                           arg = "--input.marker.list",
                           help = "List of markers (csv)",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv.annotated",
                           help = "Path to input csv where the annotated data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv.complete",
                           help = "Path to input csv where the complete data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to input csv where the results will be stored (directory).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--number.of.cores",
                           help = "For paralelization purposes (integer)",
                           type = "numeric")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--number.of.cells",
                           help = "Number of cells to be sampled per category.",
                           type = "numeric")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--selected.seed",
                           help = "Selected seed for random sampling.",
                           type = "numeric")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

MapFingerprints <- function(marker.list, # List of markers (csv).
                            input.csv.annotated, # Path to input csv where the annotated data is stored (csv).
                            input.csv.complete, # Path to input csv where the complete data is stored (csv).
                            output.folder, # Path to output directory where the figures and html will be generated (folder).
                            n.cores, # Number of cores
                            n.cells, # Number of cells to be sampled.
                            selected.seed # Selected seed
){
  if(missing(n.cells)) {
    n.cells <- 500
  }
  if(missing(selected.seed)) {
    selected.seed <- 1234
  }
  
  print(paste0('### list of markers: ', marker.list, ' ###')) 
  # marker.list <- "/media/ib/My Book Duo/output_MVM006/output_downstream_analysis/1/marker_list_path.csv"
  print(paste0('### input csv annotated: ', input.csv.annotated, ' ###')) 
  # input.csv.annotated <- "/media/ib/My Book Duo/output_MVM006/output_downstream_analysis/1/df_data_consensus.csv"
  print(paste0('### input csv complete: ', input.csv.complete, ' ###')) 
  # input.csv.complete <- "/media/ib/My Book Duo/output_MVM006/output_downstream_analysis/df_data_norm.csv"
  print(paste0('### output folder: ', output.folder, ' ###')) 
  # output.folder <- "/media/ib/My Book Duo/output_MVM006/output_downstream_analysis/1"
  print(paste0('### number of cores: ', n.cores, ' ###')) 
  # n.cores <- 10
  print(paste0('### number of sampled cells per category: ', n.cells, ' ###')) 
  # n.cells <- 500
  print(paste0('### selected seed: ', selected.seed, ' ###')) 
  # selected.seed <- 1234
  
  if(!(dir.exists(output.folder))){
    print(paste('### creating folder: ', output.folder, ' ###'))
    dir.create(output.folder, recursive = TRUE)
  }
  
  # Load exp design files ------------------------------------------------------------------
  
  print('Loading list of markers')
  
  phenotypic_markers <- read.csv(marker.list, stringsAsFactors = FALSE) %>% mutate(marker_id = toupper(marker_id)) %>%
    mutate(marker_id = toupper(gsub('-', '.', marker_id)))
  
  print(phenotypic_markers$marker_id)
  
  # Load data file ------------------------------------------------------------------
  
  print('Loading data file')
  
  df_data <- read.csv(input.csv.complete, stringsAsFactors = FALSE)
  colnames(df_data) <- lapply(colnames(df_data), function(x) toupper(gsub('-', '.', x)))
                              
  df_data <- df_data[complete.cases(df_data),]
  df_data <- df_data %>% rename(s.area = S.AREA, slide_id = SLIDE_ID, scene_id = SCENE_ID)
  
  tmp_wrong_names <- setdiff(phenotypic_markers$marker_id, colnames(df_data))
  if(length(tmp_wrong_names) > 0){
    print(paste(tmp_wrong_names, 'not found, it will not be included in the clustering.'))
    phenotypic_markers <- phenotypic_markers %>% filter(marker_id %in% colnames(df_data))
  }
  
  df_data_annotated <- read.csv(input.csv.annotated, stringsAsFactors = FALSE)
  df_data_annotated <- df_data_annotated[complete.cases(df_data_annotated),]
  
  df_data_annotated <- df_data_annotated %>% 
    left_join(df_data) %>%
    mutate(CellType = as.character(CellType))
  
  # Generate fingerprints ------------------------------------------------------------------
  
  print('Generating fingerprints')
  
  tmp_plot <- df_data_annotated %>% 
    select(CellType, phenotypic_markers$marker_id) %>%
    gather(marker, value, -CellType) %>%
    # filter(Marker %in% c('CD3', 'SOX2', 'CD34', 'CD68')) %>% 
    group_by(CellType, marker) %>% 
    summarise(M = mean(value)) %>% 
    ungroup() %>% 
    group_by(CellType) %>% 
    arrange(-M) %>% 
    mutate(Rank = 1:n()) %>% 
    ungroup()
  
  png(file.path(output.folder, 'fingerprints_annotated_celltypes.png'), width = min(n_distinct(tmp_plot$Rank)/1.5, 12), height = n_distinct(tmp_plot$CellType)/2, units = 'in', res = 300)
  print(ggplot(tmp_plot %>% filter(Rank <= 15), aes(as.factor(Rank), CellType, fill = M)) +
          geom_tile(color = "white", size = 0.1) +
          geom_text(aes(as.factor(Rank), CellType, label = marker)) +
          #coord_equal() +
          labs(x = NULL, y = NULL, title = 'Final Clusters') +
          scale_fill_gradient2(low = 'royalblue', high = 'firebrick', mid = 'gray87', midpoint = 0) +
          theme_bw() +
          theme(axis.text.x = element_text(angle = 90, hjust = 1, vjust = 0.5), plot.title = element_text(hjust = 0.5))) 
  dev.off()
  
  # uMap projection ------------------------------------------------------------------
  
  print('uMap projection')
  
  set.seed(selected.seed)
  
  tmp_reduced <- df_data_annotated %>% group_by(CellType) %>% sample_n(min(n(), n.cells)) %>% ungroup()
  tmp_matrix <- tmp_reduced %>% select(phenotypic_markers$marker_id) %>% as.matrix()
  tmp_umap <- umap(tmp_matrix, n_components = 3)
  
  tmp_plot <- tmp_reduced %>% mutate(uMap1 = tmp_umap$layout[,1], uMap2 = tmp_umap$layout[,2], uMap3 = tmp_umap$layout[,3])
  tmp_centroids <- tmp_plot %>% group_by(CellType) %>% summarise(uMap1 = median(uMap1), uMap2 = median(uMap2), uMap3 = median(uMap3)) %>% ungroup()
  
  library(plotly) 
  
  fig <-  plot_ly(data = tmp_plot, x = ~uMap1, y = ~uMap2, z = ~uMap3, color = ~CellType) %>% add_markers(size = 8)
  #Sys.setenv(PATH = paste(c(Sys.getenv("PATH"), "/usr/lib/R/bin/pandoc;"), collapse = ""))
  Sys.setenv(RSTUDIO_PANDOC="/usr/lib/R/bin/pandoc")
  htmlwidgets::saveWidget(as_widget(fig), file.path(output.folder, "umap_projection.html"))

  # Prediction uMap training ------------------------------------------------------------------
  
  print('Predicting Training Data')
  
  tmp_training <- predict(tmp_umap, df_data_annotated %>% select(phenotypic_markers$marker_id) %>% as.matrix())
  df_data_annotated <- df_data_annotated %>% 
    mutate(uMap1 = tmp_training[,1], uMap2 = tmp_training[,2], uMap3 = tmp_training[,3])
  
  library(pbapply)
  cl <- parallel::makeForkCluster(n.cores)
  # pbapply::pblapply()
  # parallel::parLapply()
  df_data_annotated <- pbapply::pblapply(X = c(1:nrow(df_data_annotated)), function(x){
    # df_predicted_clusters <- lapply(c(1:nrow(df_predicted_clusters)), function(x){
    tmp_cell <- df_data_annotated[x,]
    # tmp_fingerprints <- df_fingerprints %>% mutate(D = abs(DR1-tmp_cell$DR1) + abs(DR2-tmp_cell$DR2)) %>% group_by(cl_method) %>% filter(D == min(D)) %>% ungroup()
    tmp_training_knn <- tmp_plot %>% mutate(D = abs(uMap1-tmp_cell$uMap1) + abs(uMap2-tmp_cell$uMap2) + abs(uMap3-tmp_cell$uMap3)) %>% top_n(100, -D) %>%
      group_by(CellType) %>% summarise(N = n(), .groups = 'keep') %>% ungroup() %>% filter(N == max(N)) %>% sample_n(1) %>% ungroup() %>%
      rename(predicted.celltype = CellType)
    tmp_training_centroid <- tmp_plot %>% mutate(D = abs(uMap1-tmp_cell$uMap1) + abs(uMap2-tmp_cell$uMap2) + abs(uMap3-tmp_cell$uMap3)) %>% 
      group_by(CellType) %>% summarise(N = mean(D), .groups = 'keep') %>% ungroup() %>% mutate(M = mean(N)) %>% filter(N == min(N)) %>% sample_n(1) %>% ungroup() %>% 
      rename(predicted.celltype = CellType) %>% mutate(D = N/M)
    tmp_training <- tmp_training_knn %>% 
      cbind(tmp_training_centroid %>% rename(predicted.celltype_centroid = predicted.celltype) %>% select(-N, -M)) %>% 
      mutate(predicted.celltype = ifelse(predicted.celltype == predicted.celltype_centroid, predicted.celltype, NA)) %>% 
      select(predicted.celltype)
    return(tmp_cell %>% cbind(tmp_training))
    # }) %>% bind_rows()
  }, cl = cl) %>% bind_rows()
  parallel::stopCluster(cl)
  
  tmp_plot2 <- table(df_data_annotated[c('CellType', 'predicted.celltype')]) %>% as.data.frame() %>% 
    group_by(CellType) %>% 
    mutate(J1 = sum(Freq)) %>% 
    ungroup() %>% 
    group_by(predicted.celltype) %>% 
    mutate(J2 = sum(Freq)) %>% 
    ungroup() %>% 
    mutate(J = 2*Freq/(J1+J2))
  
  png(file.path(output.folder, 'predicted_celltypes_training.png'), width = n_distinct(tmp_plot2$CellType)/1.5, height = n_distinct(tmp_plot2$predicted.celltype)/2, units = 'in', res = 300)
  print(ggplot(tmp_plot2, aes(CellType, predicted.celltype, fill = J)) + 
          geom_tile() + 
          scale_fill_gradient(low = 'white', high = 'firebrick') + 
          theme_bw() + 
          geom_text(aes(label = Freq)) + 
          theme(axis.text.x = element_text(angle = 90, vjust = 0.5, hjust=1)))
  dev.off()
  
  print('Training Accuracy:')
  print(sum((tmp_plot2 %>% mutate(CellType =as.character(CellType), predicted.celltype = as.character(predicted.celltype)) %>% filter(CellType == predicted.celltype))$Freq)/sum(tmp_plot2$Freq))
  
  # Generate template ------------------------------------------------------------------
  
  print('Generating template')
  
  tmp_plot <- tmp_plot %>% left_join(df_data_annotated %>% select(slide_id, scene_id, OID, CellType, predicted.celltype))
  tmp_centroids <- tmp_plot %>% group_by(predicted.celltype) %>% summarise(uMap1 = median(uMap1), uMap2 = median(uMap2), uMap3 = median(uMap3)) %>% ungroup()
  
  df_data_annotated <- df_data_annotated[complete.cases(df_data_annotated),]
  tmp_plot <- tmp_plot[complete.cases(tmp_plot),]
  
  # Prediction uMap testing ------------------------------------------------------------------
  
  print('Predicting complete data')
  
  # divide into groups
  cut.factor <- 100 # potential of having more nodes than available cores, so it would loop
  cuts <- cut(1:nrow(df_data), n.cores * cut.factor)
  
  tictoc::tic()
  # conduct the parallelisation
  df_testing <- pbsapply(levels(cuts), function(x){
    tmp_data <- df_data[cuts == x,] %>% select(phenotypic_markers$marker_id) %>% as.matrix()
    tmp_meta <- df_data[cuts == x,] %>% select(slide_id, scene_id, OID)
    tmp_testing <- predict(tmp_umap, tmp_data)
    colnames(tmp_testing) <- c('uMap1', 'uMap2', 'uMap3')
    return(tmp_meta %>% cbind(tmp_testing))
  }, cl = as.integer(n.cores))# %>% bind_rows()
  tictoc::toc()
  
  df_testing <- lapply(c(1:ncol(df_testing)), function(x){
    tmp_df <- data.frame(slide_id = df_testing[1,x][[1]],
                         scene_id = df_testing[2,x][[1]],
                         OID = df_testing[3,x][[1]],
                         uMap1 = df_testing[4,x][[1]],
                         uMap2 = df_testing[5,x][[1]],
                         uMap3 = df_testing[6,x][[1]]) 
  }) %>% bind_rows()
  
  df_data <- df_data %>% left_join(df_testing) 
  df_predicted_cell_types <- df_data %>% select(slide_id, scene_id, OID, uMap1, uMap2, uMap3) 
  
  library(pbapply)
  cl <- parallel::makeForkCluster(n.cores)
  
  df_predicted_cell_types <- pbapply::pblapply(X = c(1:nrow(df_predicted_cell_types)), function(x){
    tmp_cell <- df_predicted_cell_types[x,]
    tmp_training <- tmp_plot %>% mutate(D = abs(uMap1-tmp_cell$uMap1) + abs(uMap2-tmp_cell$uMap2) + abs(uMap3-tmp_cell$uMap3)) %>% top_n(100, -D) %>%
      group_by(CellType) %>% summarise(N = n(), .groups = 'keep') %>% ungroup() %>% filter(N == max(N)) %>% sample_n(1) %>% ungroup() %>%
      select(-N)
    return(tmp_cell %>% cbind(tmp_training))
  }, cl = cl) %>% bind_rows()
  parallel::stopCluster(cl)
  
  df_data <- df_data %>% left_join(df_predicted_cell_types %>% select(slide_id, scene_id, OID, CellType))
  
  # Write annotated data ------------------------------------------------------------------
  
  print('Writing complete data')
  
  dir.create(file.path(output.folder, 'data_annotated'))
  
  df_data <- df_data %>% mutate(tissue_id = paste(slide_id, scene_id, sep = '_'))
  for(i in unique(df_data$tissue_id)){
    tmp_data <- df_data %>% filter(tissue_id == i) %>% select(-tissue_id)
    write.csv(tmp_data, file.path(output.folder, 'data_annotated', paste0(i, '.csv')), row.names = FALSE)
  }
  
  write.csv(df_data, file.path(output.folder, 'df_data_annotated.csv'), row.names = FALSE)
  
}

# Function call ------------------------------------------------------------------
MapFingerprints(marker.list = argv$input.marker.list, # Path to output folder where the results from the clustering will be stored (directory).
                input.csv.annotated = argv$path.input.csv.annotated, # Path to output folder where the results from the clustering will be stored (directory).
                input.csv.complete = argv$path.input.csv.complete, # Path to output folder where the results from the clustering will be stored (directory).
                output.folder = argv$path.output.folder, # Path to input csv where the annotations are stored (csv).
                n.cores = argv$number.of.cores, # Path to output folder where the results from the clustering will be stored (directory).
                n.cells = argv$number.of.cells,
                selected.seed = argv$selected.seed
)

# Rscript ~/Documentos/MILAN/pipeline_beta/v03/milan_pipeline/codes/cell_identification/MapFingerprints.R --input.marker.list "/media/ib/My Book Duo/output_MVM006/output_downstream_analysis/1/marker_list_path.csv" --path.input.csv.annotated "/media/ib/My Book Duo/output_MVM006/output_downstream_analysis/1/df_data_consensus.csv" --path.input.csv.complete "/media/ib/My Book Duo/output_MVM006/output_downstream_analysis/df_data_norm.csv" --path.output.folder "/media/ib/My Book Duo/output_MVM006/output_downstream_analysis/1" --number.of.cores 10 --number.of.cells 500 --selected.seed 1234 

