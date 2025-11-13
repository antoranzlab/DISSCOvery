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

tmp_parser <- arg_parser("Normalise data.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.csv",
                           help = "Path to input csv with merged data (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--normalization.yes.no",
                           help = "Binary specifying if normalization needs to be performed (binary).",
                           type = "numeric")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.csv",
                           help = "Path to output csv file where the normalized data will be stored (csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

DataNormalization <- function(input.csv, # Path to input csv with merged data (csv).
                              normalization.yes.no, # Binary specifying if normalization needs to be performed (binary).
                              output.csv # Path to output csv file where the normalized data will be stored (csv).
){
  print(paste0('### input csv: ', input.csv, ' ###')) 
  print(paste0('### normalization.yes.no: ', normalization.yes.no, ' ###')) 
  print(paste0('### output csv: ', output.csv, ' ###')) 

  if(!(dir.exists(dirname(output.csv)))){
    print(paste('### creating folder: ', dirname(output.csv), ' ###'))
    dir.create(dirname(output.csv), recursive = TRUE)
  }
  
  # Load csv ------------------------------------------------------------------
  
  print('Loading csv')
  
  df_data <- read.csv(input.csv, stringsAsFactors = FALSE)
  
  
  # Normalize MFIs ------------------------------------------------------------------
  
  if(as.numeric(normalization.yes.no) == TRUE){
    print('Normalizing Intensity Values (z-scores)')
    
    df_data <- df_data %>% 
      # gather(marker, value, -slide_id, -scene_id, -OID, -X, -Y, -s.area) %>% 
      gather(marker, value, -slide_id, -scene_id, -OID, -X, -Y, -s.area, -scan_region) %>% 
      mutate(value = ifelse(is.na(value), 0, value))
    
    df_data <- df_data %>% 
      group_by(marker, slide_id, scene_id) %>% 
      mutate(value = scale(value)) %>% 
      ungroup() %>% 
      mutate(value = ifelse(value > 5, 5, value),
             value = ifelse(value < -5, -5, value))
    
    df_data <- df_data %>% 
      spread(marker, value)
  }
  
  # Write csv ------------------------------------------------------------------
  
  print('Writing csv')
  
  write.csv(df_data, output.csv, row.names = FALSE)
  
}

# Parser check -------------------------------------------------------------------
required_args <- c("path.input.csv", "normalization.yes.no", "path.output.csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
DataNormalization(input.csv = argv$path.input.csv, # Path to input csv file (csv file). Example: /path/to/project_directory/output_cell_identification/df_data_merged.csv
                  normalization.yes.no = argv$normalization.yes.no, # Normalization yes (1) or no (0). Example: 1
                  output.csv = argv$path.output.csv # Path to output csv with normalized data (csv). Example: /path/to/project_directory/output_cell_identification/n01/df_data_norm.csv
)
