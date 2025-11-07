#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

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

tmp_parser <- arg_parser("Data Filtering")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.folder",
                           help = "Path to input directory where the annotated data is stored (dir).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.split.celltypes",
                           help = "Path to input directory where the selected celltypes are listed (.csv).",
                           type = "character")
                           
tmp_parser <- add_argument(tmp_parser,
                          arg = "--path.output.csv",
                           help = "Path to output csv where the split data will be stored (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

DataFiltering <- function(input.folder, # Path to input directory where the annotated data is stored (folder).
                          split.celltypes, # Path to output directory where the figures and html will be generated (folder).
                          output.csv # Path to input directory where the temp results were stored (directory).
){
  print(paste0('### input folder: ', input.folder, ' ###')) 
  print(paste0('### split celltypes: ', split.celltypes, ' ###')) 
  print(paste0('### output data: ', output.csv, ' ###')) 

  if(!(dir.exists(dirname(output.csv)))){
    print(paste('### creating folder: ', dirname(output.csv), ' ###'))
    dir.create(dirname(output.csv), recursive = TRUE)
  }
  
  # Load data ------------------------------------------------------------------
  
  print('Reading data')
  
  tmp_files <- list.files(input.folder, full.names = TRUE)
  
  df_data <- lapply(tmp_files, read.csv) %>% bind_rows()
  
  df_celltypes <- read.csv(split.celltypes) %>% filter(include == 1)
  
  # Filter data ------------------------------------------------------------------
  
  print('Filtering data')
  
  df_data <- df_data %>% 
    filter(CellType %in% unique(df_celltypes$CellType)) %>% 
    select(-uMap1, -uMap2, -uMap3, -CellType)
  
  # Write data ------------------------------------------------------------------
  
  print('Writing data')
  
  write.csv(df_data, output.csv, row.names = FALSE)
  
}



# Parser check -------------------------------------------------------------------
required_args <- c("path.input.folder", "path.split.celltypes", "path.output.csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


                                 
# Function call ------------------------------------------------------------------
DataFiltering(input.folder = argv$path.input.folder, # Path to input directory where the annotated data is stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01/data_annotated
              split.celltypes = argv$path.split.celltypes, # Path to input directory where the selected celltypes are listed (.csv). Example: /path/to/project_directory/output_cell_identification/n01/selected_celltypes_c01.csv
              output.csv = argv$path.output.csv # Path to output csv where the split data will be stored (.csv). Example: /path/to/project_directory/output_cell_identification/n01/c01/merged_data_c01.csv
)

