#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

list.of.packages <- c("tidyverse", "EBImage", "argparser", 'doSNOW', 'readxl', 'pastecs', 'graphics', 'pbapply', 'parallel', 'reticulate')
new.packages <- list.of.packages[!(list.of.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)) install.packages(new.packages, repos = "http://cran.us.r-project.org")

list.of.bioconductor.packages <- c('EBImage')
new.packages <- list.of.packages[!(list.of.bioconductor.packages %in% installed.packages()[,"Package"])]
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
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Sample data prior to clustering and dimensionality reduction.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv",
                           help = "Path to input csv file with the normalized data (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.csv",
                           help = "Path to output csv where sampled data will be stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--sampling.yes.no",
                           help = "Binary specifying if sampling needs to be performed (binary).",
                           type = "numeric")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--number.of.cells",
                           help = "Number of cells to be sampled.",
                           type = "numeric")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--selected.seed",
                           help = "Selected seed for random sampling.",
                           type = "numeric")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

DataSampling <- function(input.csv, # Path to input csv file with the normalized data (csv).
                         output.csv, # Path to output csv file where the normalized data will be stored (csv).
                         sampling.yes.no, # Binary specifying if sampling needs to be performed (binary).
                         n.cells, # Number of cells to be sampled.
                         selected.seed # Selected seed
){
  
  if(missing(n.cells)) {
    n.cells <- 25000
  }
  
  if(missing(selected.seed)) {
    selected.seed <- 1234
  }
   
  if(missing(sampling.yes.no)) {
    sampling.yes.no <- 1
  }
  
  print(paste0('### input normalized data: ', input.csv, ' ###')) 
  print(paste0('### output sampled data: ', output.csv, ' ###')) 
  print(paste0('### sampling.yes.no: ', sampling.yes.no, ' ###')) 
  print(paste0('### number of sampled cells: ', n.cells, ' ###')) 
  print(paste0('### selected seed: ', selected.seed, ' ###')) 

  if(!(dir.exists(dirname(output.csv)))){
    print(paste('### creating folder: ', dirname(output.csv), ' ###'))
    dir.create(dirname(output.csv), recursive = TRUE)
  }
  
  # Load norm data ------------------------------------------------------------------
  
  print('Loading normalized data')
  
  df_data <- read.csv(input.csv, stringsAsFactors = FALSE)
  df_data <- df_data[complete.cases(df_data),]
  
  # Sample cells ------------------------------------------------------------------
  
  if(as.numeric(sampling.yes.no) == TRUE){
    print('Sampling cells')
    
    tmp_cell <- df_data %>% 
      group_by(slide_id, scene_id) %>% 
      summarise(N = n()) %>% 
      ungroup() %>% 
      mutate(M = sum(N)) %>% 
      mutate(P = N/M) %>% 
      mutate(sample_size = n.cells*P) %>% 
      select(slide_id, scene_id, sample_size)
    
    set.seed(selected.seed)
    
    df_data <- df_data %>% 
      left_join(tmp_cell) %>% 
      group_by(slide_id, scene_id) %>% 
      sample_n(min(n(), unique(round(sample_size)))) %>% 
      ungroup() %>% 
      select(-sample_size)
  }
  
  write.csv(df_data, output.csv, row.names = FALSE)
  
}


# Parser check -------------------------------------------------------------------
required_args <- c("path.input.csv", "path.output.csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}



# Function call ------------------------------------------------------------------
DataSampling(input.csv = argv$path.input.csv, # Path to input csv (csv). Example: /path/to/project_directory/output_cell_identification/n01/df_data_norm.csv
             output.csv = argv$path.output.csv, # Path to output csv where sampled data will be stored (csv). Example: /path/to/project_directory/output_cell_identification/n01/df_data_sampled.csv
             sampling.yes.no = argv$sampling.yes.no, # Binary specifying if sampling needs to be performed (binary). Example: 1
             n.cells = argv$number.of.cells, # Number of cells to be sampled (integer). Example: 25000
               selected.seed = argv$selected.seed # Seed for sampling. Example: 1234
)
