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

tmp_parser <- arg_parser("Merge csv files into a single file.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.folder",
                           help = "Path to input folder with csv files (directory).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.exp.design.scenes",
                           help = "Path to input with the experimental design regarding scenes (xlsx).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.qc",
                           help = "Path to output qc file where the quality control will be stored (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.csv",
                           help = "Path to output csv file where the merged data will be stored (csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

MergeData <- function(input.folder, # Path to input folder with csv files (directory).
                      input.exp.design.scenes, # Path to input with the experimental design regarding scenes (xlsx).
                      output.qc, # Path to output QC where the complete cases will be reported (csv).
                      output.csv # Path to output csv file where the normalized data will be stored (csv).
){
  print(paste0('### input csv folder: ', input.folder, ' ###')) 
  print(paste0('### input exp design scenes: ', input.exp.design.scenes, ' ###')) 
  print(paste0('### output qc: ', output.qc, ' ###')) 
  print(paste0('### output csv: ', output.csv, ' ###')) 

  if(!(dir.exists(dirname(output.csv)))){
    print(paste('### creating folder: ', dirname(output.csv), ' ###'))
    dir.create(dirname(output.csv), recursive = TRUE)
  }
  
  # Load exp design ------------------------------------------------------------------
  
  print('Loading experimental design')
  
  tmp_exp_design_scenes <- readxl::read_excel(input.exp.design.scenes) %>%
    filter(QC_include == 1)
  
  # Load csv files ------------------------------------------------------------------
  
  print('Loading csv files')
  
  tmp_files <- list.files(input.folder)
  
  df_data <- data.frame()
  
  for(i in tmp_files){
    tmp_data <- read.csv2(file.path(input.folder, i), stringsAsFactors = FALSE)
    df_data <- df_data %>% bind_rows(tmp_data)
  }
  
  # QC complete data
  
  df_data <- df_data[complete.cases(df_data),]
  
  print('QC complete data')
  print(paste(nrow(tmp_exp_design_scenes), 'scenes included in the experimental desing'))
  print(paste(length(tmp_files), 'scenes with partial data (csv generated from feature extraction)'))
  print(paste(n_distinct(paste(df_data$slide_id, df_data$scene_id)), 'scenes with complete data'))
  
  tmp_qc <- tmp_exp_design_scenes %>% select(slide_name, scene_number) %>% unique() %>% 
    left_join(df_data %>% select(slide_id, scene_id) %>% rename(slide_name = slide_id, scene_number = scene_id) %>% 
                mutate(scene_number = as.numeric(sub('scene', '', scene_number))) %>% mutate(QC = 1) %>% unique())
  write.csv(tmp_qc, output.qc, row.names = FALSE)
  
  # Write Data ------------------------------------------------------------------
  
  print('Writting Data')
  
  df_data <- df_data %>% 
    gather(marker, value, -slide_id, -scene_id, -OID, -X, -Y, -s.area) %>% 
    mutate(value = ifelse(is.na(value), 0, value)) %>% 
    spread(marker, value)
  
  write.csv(df_data, output.csv, row.names = FALSE)
  
}

# Parser check -------------------------------------------------------------------
required_args <- c("path.input.folder", "path.input.exp.design.scenes", "path.output.qc", "path.output.csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
MergeData(input.folder = argv$path.input.folder, # Path to input csv files (dir). Example: /path/to/project_directory/output_feature_extraction/feature_extraction.csv
          input.exp.design.scenes = argv$path.input.exp.design.scenes, # Path to input excel with experimental design for the scenes (.csv). Example: /path/to/project_directory/experimental_design/exp_design_scenes.xlsx
          output.qc = argv$path.output.qc, # Path to output quality control file (.csv). Example: /path/to/project_directory/output_cell_identification/df_data_qc.csv
          output.csv = argv$path.output.csv # Path to output csv with merged data (.csv). Example: /path/to/project_directory/output_cell_identification/df_data_merged.csv
)