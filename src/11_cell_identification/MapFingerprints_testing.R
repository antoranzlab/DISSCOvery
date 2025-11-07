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

tmp_parser <- arg_parser("MapFingerprints Testing")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input.marker.list",
                           help = "List of markers (.csv)",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv.training",
                           help = "Path to input csv where the training data is stored (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv.testing",
                           help = "Path to input csv where the testing data is stored (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.model",
                           help = "Path to input rds where the model umap is stored (rds).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to input csv where the results will be stored (dir).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

MapFingerprints_testing <- function(marker.list, # List of markers (csv).
                                    input.csv.training, # Path to input csv where the annotated data is stored (csv).
                                    input.model, # Path to the umap where the projection will be done (rds).
                                    input.csv.testing, # Path to input csv where the complete data is stored (csv).
                                    output.folder # Path to output directory where the figures and html will be generated (dir).
){
  print(paste0('### list of markers: ', marker.list, ' ###')) 
  print(paste0('### input csv training: ', input.csv.training, ' ###')) 
  print(paste0('### input csv testing: ', input.csv.testing, ' ###')) 
  print(paste0('### input model: ', input.model, ' ###')) 
  print(paste0('### output folder: ', output.folder, ' ###')) 

  if(!(dir.exists(output.folder))){
    print(paste('### creating folder: ', output.folder, ' ###'))
    dir.create(output.folder, recursive = TRUE)
  }
  
  # Load exp design files ------------------------------------------------------------------
  
  print('Loading list of markers')
  
  phenotypic_markers <- read.csv(marker.list, stringsAsFactors = FALSE) %>% mutate(marker_id = toupper(marker_id)) %>%
    mutate(marker_id = toupper(gsub('-', '.', marker_id)))
  
  # Load data file ------------------------------------------------------------------
  
  print('Loading data files')
  
  tmp_plot <- read.csv(input.csv.training, stringsAsFactors = FALSE)
  df_data <- read.csv(input.csv.testing, stringsAsFactors = FALSE)
  tmp_umap <- readRDS(input.model)   
     
  tmp_wrong_names <- setdiff(phenotypic_markers$marker_id, colnames(df_data))
  if(length(tmp_wrong_names) > 0){
    print(paste(tmp_wrong_names, 'not found, it will not be included in the clustering.'))
    phenotypic_markers <- phenotypic_markers %>% filter(marker_id %in% colnames(df_data))
  }      
  
  # Prediction uMap testing ------------------------------------------------------------------
  
  print('Predicting complete data')
  
  tmp_data <- df_data %>% select(phenotypic_markers$marker_id) %>% as.matrix()
  tmp_meta <- df_data %>% select(slide_id, scene_id, OID)
  tmp_testing <- predict(tmp_umap, tmp_data)
  colnames(tmp_testing) <- c('uMap1', 'uMap2', 'uMap3')
  
  df_data <- df_data %>% cbind(tmp_testing) 
  df_predicted_cell_types <- df_data %>% select(slide_id, scene_id, OID, uMap1, uMap2, uMap3) 
  
  df_predicted_cell_types <- lapply(c(1:nrow(df_predicted_cell_types)), function(x){
    tmp_cell <- df_predicted_cell_types[x,]
    tmp_training <- tmp_plot %>% mutate(D = abs(uMap1-tmp_cell$uMap1) + abs(uMap2-tmp_cell$uMap2) + abs(uMap3-tmp_cell$uMap3)) %>% top_n(25, -D) %>%
      group_by(CellType) %>% summarise(N = n(), .groups = 'keep') %>% ungroup() %>% filter(N == max(N)) %>% sample_n(1) %>% ungroup() %>%
      select(-N)
    return(tmp_cell %>% cbind(tmp_training))
  }) %>% bind_rows()
  
  df_data <- df_data %>% left_join(df_predicted_cell_types %>% select(slide_id, scene_id, OID, CellType))
  
  # Write annotated data ------------------------------------------------------------------
  
  print('Writing csv')
  
  tmp_basename <- basename(input.csv.testing)
  
  write.csv(df_data, file.path(output.folder, tmp_basename), row.names = FALSE)
  
}

# Parser check -------------------------------------------------------------------
required_args <- c("input.marker.list", "path.input.csv.training", "path.input.csv.testing", "path.input.model", "path.output.folder")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
MapFingerprints_testing(marker.list = argv$input.marker.list, # Path to the csv where the markers used for clustering are defined (.csv). Example: /path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv
                        input.csv.training = argv$path.input.csv.training, # Path to the csv with the training data (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/tmp_results/training_data.csv
                        input.csv.testing = argv$path.input.csv.testing, # Path to the input csv where the training data is stored (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions/iter_1.csv
                        input.model = argv$path.input.model, # Path to input csv where the complete data is stored (.rds). Example: /path/to/project_directory/output_cell_identification/n01/v01/tmp_results/tmp_umap.rds
                        output.folder = argv$path.output.folder # Path to the output directory where the results will be stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions_annotated
)
