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
                           arg = "--path.input.csv.colors",
                           help = "Path to input csv where the selected colors are stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv",
                           help = "Path to input csv where the data is stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.segmented.dapi",
                           help = "Path to input npy where the segmented DAPI object is stored (npy).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to input csv where the results will be stored (directory).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

DigitalReconstruction <- function(input.csv.colors, # Path to input csv where the annotated data is stored (csv).
                                  input.segmented.dapi, # Path to input npy where the segmented object is stored (npy).
                                  input.csv, # Path to input csv where the data is stored (csv).
                                  output.folder # Path to output directory where the figures and html will be generated (folder).
){
  print(paste0('### input csv colors: ', input.csv.colors, ' ###')) 
  print(paste0('### input csv data: ', input.csv, ' ###')) 
  print(paste0('### input segmented object: ', input.segmented.dapi, ' ###')) 
  print(paste0('### output folder: ', output.folder, ' ###')) 

  if(!(dir.exists(output.folder))){
    print(paste('### creating folder: ', output.folder, ' ###'))
    dir.create(output.folder, recursive = TRUE)
  }
  
  # Load exp design files ------------------------------------------------------------------
  
  print('Loading colors')
  
  df_dictionary <- read.csv(input.csv.colors, stringsAsFactors = FALSE) %>% 
    mutate(CellType = as.character(CellType)) %>%
    mutate(R = as.numeric(R), B = as.numeric(B), G = as.numeric(G)) # %>%

  print(df_dictionary)
  
  # Load data ------------------------------------------------------------------
  
  print('Loading data')
  
  df_data <- read.csv(input.csv, stringsAsFactors = FALSE) %>%
    mutate(CellType = as.character(CellType)) %>%
    mutate(tissue_id = paste(slide_id, scene_id, sep = '_')) %>%
    left_join(df_dictionary)
  
  # Load segmentation matrix ------------------------------------------------------------------
  
  print('Loading segmentation matrix')
  
  segmentation_matrix <- readRDS(file = input.segmented.dapi)
  
  # Generate digital tissue ------------------------------------------------------------------
  
  print('Generating digital tissue')
  
  tmp_red <- matrix(0, nrow = nrow(segmentation_matrix), ncol = ncol(segmentation_matrix))
  tmp_green <- matrix(0, nrow = nrow(segmentation_matrix), ncol = ncol(segmentation_matrix))
  tmp_blue <- matrix(0, nrow = nrow(segmentation_matrix), ncol = ncol(segmentation_matrix))
  
  for(j in sort(unique(df_dictionary$CellType))){
    tmp_data <- df_data %>% filter(CellType == j)
    tmp_colors <- df_dictionary %>% filter(CellType == j) %>% select(R, G, B) %>% unique()
    tmp_image <- dilate(segmentation_matrix)
    tmp_image[!(tmp_image %in% tmp_data$OID2)] <- 0
    tmp_image[tmp_image>0] <- 1
    tmp_red <- tmp_red + tmp_colors$R*tmp_image
    tmp_green <- tmp_green + tmp_colors$G*tmp_image
    tmp_blue <- tmp_blue + tmp_colors$B*tmp_image
  }
  
  tmp_plot <- EBImage::rgbImage(red = tmp_red,
                                green = tmp_green,
                                blue = tmp_blue)
  tmp_plot = paintObjects(segmentation_matrix, tmp_plot, col='black')
  
  # Save results ------------------------------------------------------------------
  
  print('Saving results')
  
  EBImage::writeImage(x = tmp_plot, files = file.path(output.folder, paste0(unique(df_data$tissue_id), '.tiff')), type = 'tiff', compression = 'LZW')
  
}

# Parser check -------------------------------------------------------------------
required_args <- c("path.input.csv.colors", "path.input.segmented.dapi", "path.input.csv", "path.output.folder")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
DigitalReconstruction(input.csv.colors = argv$path.input.csv.colors, # Path to input csv where the annotated data is stored (csv). Example:  path/to/project_directory/utput_downstream_analysis/1/df_consensus_celltypes_colored.csv
                      input.segmented.dapi = argv$path.input.segmented.dapi, # path to the segmentation DAPI matrix RDS file (rds). Example:  path/to/project_directory/output_downstream_analysis/1/digital_tissue_aux/MVM006_scene01.rds
                      input.csv = argv$path.input.csv, # Path to the csv with the colors for the celltypes. (csv). Example:  path/to/project_directory/output_downstream_analysis/1/digital_tissue_aux/MVM006_scene01.csv
                      output.folder = argv$path.output.folder # Path to the output folder where the results will be stored (dir). Example:  path/to/project_directory/output_downstream_analysis/1/digital_tissue
)


