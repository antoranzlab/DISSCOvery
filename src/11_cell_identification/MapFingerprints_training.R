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

list.of.bioconductor.packages <- c('EBImage')
new.packages <- list.of.bioconductor.packages[!(list.of.bioconductor.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)){
  if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager")
  BiocManager::install(new.packages)
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
library(plotly) 

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("MapFingerprints_training.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input.marker.list",
                           help = "List of markers (.csv)",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv.annotated",
                           help = "Path to input csv where the annotated data is stored (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv.complete",
                           help = "Path to input csv where the complete data is stored (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to output directory where the results will be stored (dir).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.partitions",
                           help = "Path to output directory where the partitions of the complete data will be stored (dir).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.tmp.results",
                           help = "Path to output directory where the temporary results will be stored (dir).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--number.of.cores",
                           help = "Number of cores for the training for paralelization purposes (integer)",
                           type = "numeric")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--number.of.cells",
                           help = "Number of cells to be sampled per category (integer).",
                           type = "numeric")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--selected.seed",
                           help = "Selected seed for random sampling (integer).",
                           type = "numeric")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

MapFingerprints_training <- function(marker.list, # List of markers (csv).
                                     input.csv.annotated, # Path to input csv where the annotated data is stored (csv).
                                     input.csv.complete, # Path to input csv where the complete data is stored (csv).
                                     output.folder, # Path to output directory where the figures and html will be generated (dir).
                                     output.partitions, # Path to output directory where the csv partitions will be generated (dir).
                                     output.tmp.results, # Path to output directory where the tmp results will be stored (dir).
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
  print(paste0('### input csv annotated: ', input.csv.annotated, ' ###')) 
  print(paste0('### input csv complete: ', input.csv.complete, ' ###')) 
  print(paste0('### output folder: ', output.folder, ' ###')) 
  print(paste0('### output partitions: ', output.partitions, ' ###')) 
  print(paste0('### output temporary results: ', output.tmp.results, ' ###')) 
  print(paste0('### number of cores: ', n.cores, ' ###')) 
  print(paste0('### number of sampled cells per category: ', n.cells, ' ###')) 
  print(paste0('### selected seed: ', selected.seed, ' ###')) 
  n.cores <- as.integer(n.cores)
  n.cells <- as.integer(n.cells)
  selected.seed <- as.integer(selected.seed)

  if(!(dir.exists(output.folder))){
    print(paste('### creating folder: ', output.folder, ' ###'))
    dir.create(output.folder, recursive = TRUE)
  }
  
  if(!(dir.exists(output.partitions))){
    print(paste('### creating folder: ', output.partitions, ' ###'))
    dir.create(output.partitions, recursive = TRUE)
  }
  
  if(!(dir.exists(output.tmp.results))){
    print(paste('### creating folder: ', output.tmp.results, ' ###'))
    dir.create(output.tmp.results, recursive = TRUE)
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
  # tmp_centroids <- tmp_plot %>% group_by(CellType) %>% summarise(uMap1 = median(uMap1), uMap2 = median(uMap2), uMap3 = median(uMap3)) %>% ungroup()
  tmp_training_centroid <- tmp_plot %>% group_by(CellType) %>% summarise(uMap1 = median(uMap1), uMap2 = median(uMap2), uMap3 = median(uMap3)) %>%
    ungroup() %>% rename(predicted.celltype = CellType)
  
  fig <-  plot_ly(data = tmp_plot, x = ~uMap1, y = ~uMap2, z = ~uMap3, color = ~CellType) %>% add_markers(size = 8)
  Sys.setenv(RSTUDIO_PANDOC="/usr/lib/R/bin/pandoc")
  htmlwidgets::saveWidget(as_widget(fig), file.path(output.folder, "umap_projection.html"))

  # Prediction uMap training ------------------------------------------------------------------
  
  print('Predicting Training Data')
  
  tmp_training <- predict(tmp_umap, df_data_annotated %>% select(phenotypic_markers$marker_id) %>% as.matrix())
  df_data_annotated <- df_data_annotated %>% 
    mutate(uMap1 = tmp_training[,1], uMap2 = tmp_training[,2], uMap3 = tmp_training[,3])
  
  df_data_annotated <- pblapply(c(1:nrow(df_data_annotated)), function(x){
    tmp_cell <- df_data_annotated[x,]
    tmp_training_knn <- tmp_plot %>% mutate(D = abs(uMap1-tmp_cell$uMap1) + abs(uMap2-tmp_cell$uMap2) + abs(uMap3-tmp_cell$uMap3)) %>% top_n(25, -D) %>%
      group_by(CellType) %>% summarise(N = n(), .groups = 'keep') %>% ungroup() %>% filter(N == max(N)) %>% sample_n(1) %>% ungroup() %>%
      rename(predicted.celltype = CellType)
    tmp_training <- tmp_training_knn %>% 
      cbind(tmp_training_centroid %>% rename(predicted.celltype_centroid = predicted.celltype)) %>%
      # cbind(tmp_training_centroid %>% rename(predicted.celltype_centroid = celltype) %>% select(-N, -M)) %>% 
      mutate(predicted.celltype = ifelse(predicted.celltype == predicted.celltype_centroid, predicted.celltype, NA)) %>% 
      select(predicted.celltype)
    return(tmp_cell %>% mutate(predicted.celltype = tmp_training_knn$predicted.celltype))
  }) %>% bind_rows()
  
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
  
  # Save intermediate results
  
  print('Save temporary results')
  
  write.csv(tmp_plot, file.path(output.tmp.results, 'training_data.csv'), row.names = FALSE)
  saveRDS(tmp_umap, file.path(output.tmp.results, 'tmp_umap.rds'))
  
  # divide into groups
  cut.factor <- 10 # potential of having more nodes than available cores, so it would loop
  cuts <- cut(1:nrow(df_data), n.cores * cut.factor)
  
  tmp_iter <- 1
  for(i in unique(cuts)){
    tmp_data <- df_data[cuts == i,]
    write.csv(tmp_data, file.path(output.partitions, paste0('iter_', tmp_iter, '.csv')), row.names = FALSE)
    tmp_iter <- tmp_iter + 1
  }
  
  tmp_list <- list.files(output.partitions, full.names = TRUE)
  
  tmp_csv <- data.frame(input.markers = marker.list,
                        input.training = file.path(output.tmp.results, 'training_data.csv'),
                        input.model = file.path(output.tmp.results, 'tmp_umap.rds'),
                        input.testing = tmp_list)
  write.csv(tmp_csv, file.path(output.tmp.results, 'auxiliary_csv.csv'), row.names = FALSE)
}


# Parser check -------------------------------------------------------------------
required_args <- c("input.marker.list", "path.input.csv.annotated", "path.input.csv.complete", "path.output.folder", "path.output.partitions", "path.output.tmp.results",
                   "number.of.cores")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
MapFingerprints_training(marker.list = argv$input.marker.list, # Path to the csv where the markers used for clustering are defined (.csv). Example: /path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv
                         input.csv.annotated = argv$path.input.csv.annotated, # Path to the csv with the annotated data (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/df_data_consensus.csv
                         input.csv.complete = argv$path.input.csv.complete, # Path to input csv with complete data (normalized data). Example: /path/to/project_directory/output_cell_identification/n01/df_data_norm.csv
                         output.folder = argv$path.output.folder, # Path to output folder with some temporal data will be stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01
                         output.partitions = argv$path.output.partitions, # Path to output directory where partition data will be stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions
                         output.tmp.results = argv$path.output.tmp.results, # Path to output directory where the intermediate results will be stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01/tmp_results
                         n.cores = argv$number.of.cores, # Number of cores for the training (integer). Example: 10
                         n.cells = argv$number.of.cells, # Number of cells from each category sampled to generate the umap template (integer). Example: 2500
                         selected.seed = argv$selected.seed # Seed for reproducibility (integer). Example: 1234
)

marker.list = '/home/luna.kuleuven.be/u0172795/Documents/DISSCOvery/test_MILAN_September/output_cell_identification/phenotypic_markers_n01_v01.csv'
input.csv.annotated = '/home/luna.kuleuven.be/u0172795/Documents/DISSCOvery/test_MILAN_September/output_cell_identification/n01/v01/df_data_consensus.csv'
input.csv.complete = '/home/luna.kuleuven.be/u0172795/Documents/DISSCOvery/test_MILAN_September/output_cell_identification/n01/df_data_norm.csv'
output.folder = '/home/luna.kuleuven.be/u0172795/Documents/DISSCOvery/test_MILAN_September/output_cell_identification/n01/v01/'
output.partitions = '/home/luna.kuleuven.be/u0172795/Documents/DISSCOvery/test_MILAN_September/output_cell_identification/n01/v01/tmp_partitions'
output.tmp.results = '/home/luna.kuleuven.be/u0172795/Documents/DISSCOvery/test_MILAN_September/output_cell_identification/n01/v01/tmp_results'
n.cores = '2'
n.cells = '100'
selected.seed = '1234'