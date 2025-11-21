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

tmp_parser <- arg_parser("Digital Reconstruction.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv.scene",
                           help = "Path to input csv where the annotated data for the scene is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.segmented.dapi",
                           help = "Path to input npy where the segmented DAPI object is stored (npy).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.overlapping.mask",
                           help = "Path to input tiff where the overlapping mask is stored (tiff).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to input csv where the results will be stored (directory).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

DigitalReconstructionAux <- function(input.csv.scene, # Path to input csv where the complete data is stored (csv).
                                     input.segmented.dapi, # Path to input npy where the segmented object is stored (npy).
                                     input.overlapping.mask, # Path to input tiff where the overlapping mask is stored (npy).
                                     output.folder # Path to output directory where the figures and html will be generated (dir).
){
  print(paste0('### input csv scene: ', input.csv.scene, ' ###')) 
  print(paste0('### input segmented object: ', input.segmented.dapi, ' ###')) 
  print(paste0('### input overlapping mask: ', input.overlapping.mask, ' ###')) 
  print(paste0('### output folder: ', output.folder, ' ###')) 

  if(!(dir.exists(output.folder))){
    print(paste('### creating folder: ', output.folder, ' ###'))
    dir.create(output.folder, recursive = TRUE)
  }
  
  # Load data file ------------------------------------------------------------------
  
  print('Loading data file')
  
  df_data <- read.csv(input.csv.scene, stringsAsFactors = FALSE) %>% 
    mutate(tissue_id = paste(slide_id, scene_id, sep = '_'))
  
  # Load segmented object ------------------------------------------------------------------
  
  print('Loading segmented object')
  
  np <- import("numpy")
  
  segmentation_matrix <- np$load(input.segmented.dapi) %>% t()
    
  # Load OVL mask ------------------------------------------------------------------
  
  print('Loading overlapping mask')
  
  tmp_mask <- EBImage::readImage(input.overlapping.mask)

  # Apply QC filters ------------------------------------------------------------------
  
  print('Applying QC filters')
  
  tmp_objects <- EBImage::bwlabel(tmp_mask)
  tmp_df_objects <- reshape::melt(tmp_objects) %>% 
    as.data.frame() %>% 
    filter(value != 0) %>%  
    group_by(value) %>% 
    mutate(N = n()) %>% 
    ungroup() %>% 
    mutate(M = n()) %>% 
    filter(N/M > 1/100) %>% 
    select(-N) %>% 
    summarise(value = unique(value), x1.min = min(X1), x1.max = max(X1), x2.min = min(X2), x2.max = max(X2))
  
  tmp_mask[tmp_objects != tmp_df_objects$value] <- 0
  tmp_mask <- dilate(tmp_mask)
  tmp_mask <- tmp_mask[unique(tmp_df_objects$x1.min):unique(tmp_df_objects$x1.max), unique(tmp_df_objects$x2.min):unique(tmp_df_objects$x2.max)]
  tmp_mask <- dilate(tmp_mask)
  
  segmentation_matrix <- segmentation_matrix[unique(tmp_df_objects$x1.min):unique(tmp_df_objects$x1.max), unique(tmp_df_objects$x2.min):unique(tmp_df_objects$x2.max)]
  segmentation_matrix <- segmentation_matrix*tmp_mask
  
  # Identify objects in space ------------------------------------------------------------------
  
  print('Identifying objects in space')
  
  tmp_sizes <- table(segmentation_matrix) %>% as.data.frame()
  tmp_sizes <- tmp_sizes %>% filter(segmentation_matrix != 0)

  segmentation_matrix[!(segmentation_matrix %in% tmp_sizes$segmentation_matrix)] <- 0

  df_data <- lapply(c(1:nrow(df_data)), function(x){
    tmp_cell <- df_data[x,]
    tmp_oid2 <- segmentation_matrix[tmp_cell$Y, tmp_cell$X]
    tmp_cell <- tmp_cell %>% mutate(OID2 = tmp_oid2)
    return(tmp_cell)
  }) %>% bind_rows()
  
  
  # Save results ------------------------------------------------------------------
  
  print('Saving results')
  
  write.csv(df_data, file.path(output.folder, paste0(unique(df_data$tissue_id), '.csv')), row.names = FALSE)
  
  segmentation_matrix[!(segmentation_matrix %in% df_data$OID2)] <- 0
  saveRDS(object = segmentation_matrix, file = file.path(output.folder, paste0(unique(df_data$tissue_id), '.rds')))
  
}
  
# Parser check -------------------------------------------------------------------
required_args <- c("path.input.csv.scene", "path.input.segmented.dapi", "path.input.overlapping.mask", "path.output.folder")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
DigitalReconstructionAux(input.csv.scene = argv$path.input.csv.scene, # Path to input csv where the complete data is stored (csv). Example:  path/to/project_directory/output_digital_reconstruction/v02/cell_annotations/TMA_scene05.csv
                         input.segmented.dapi = argv$path.input.segmented.dapi, # Path to input npy where the segmented object is stored (npy). Example: path/to/project_directory/output_segmentation/Matrix/TMA_20210101_R01_V02_S4_DAPI.npy
                         input.overlapping.mask = argv$path.input.overlapping.mask, # Path to input tiff where the overlapping mask is stored (tiff). Example: path/to/project_directory/output_overlapping_QC/TMA_scene05.tiff
                         output.folder = argv$path.output.folder # Path to output directory where the figures and html will be generated (dir). Example: path/to/project_directory/output_digital_reconstruction/v02/digital_tissue_aux
)
