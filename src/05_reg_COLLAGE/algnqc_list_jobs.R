#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("ALGNQC - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_images",
                           help = "Path to input tiles (dir).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder_csv",
                           help = "Path to output path to save csv (dir).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder_html",
                           help = "Path to output path to save html (dir).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder_json",
                           help = "Path to output path to save json (dir).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path_model",
                           help = "Path to input ALGNQC model (.h5).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_round",
                           help = "Reference round (str).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_version",
                           help = "Reference version (str).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_channel",
                           help = "Reference channel (str).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

ALGNQCJobList <- function(input_path_images, # Path to input images (path).
                          output_folder_csv, # Path to output path to save csv (path).
                          output_folder_html, # Path to output path to save html (path).
                          output_folder_json, # Path to output path to save json (path).
                          path_model, # Path to the ALGNQC model (.h5).
                          ref_round, # Reference round
                          ref_version, # Reference version
                          ref_channel, # Reference channel
                          output_path_csv # Path to output csv where the job list will be saved (.csv).
){
  print(paste0('### input path images: ', input_path_images, ' ###')) 
  print(paste0('### output directory (csv): ', output_folder_csv, ' ###'))
  print(paste0('### output directory (html): ', output_folder_html, ' ###'))
  print(paste0('### output directory (csv): ', output_folder_json, ' ###'))
  print(paste0('### path to model: ', path_model, ' ###')) 
  print(paste0('### reference round: ', ref_round, ' ###')) 
  print(paste0('### reference version: ', ref_version, ' ###')) 
  print(paste0('### reference channel: ', ref_channel, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 

  
  if(!(dir.exists(output_folder_csv))){
    print(paste('### creating folder: ', output_folder_csv, ' ###'))
    dir.create(output_folder_csv, recursive = TRUE)
  }
  
  if(!(dir.exists(output_folder_html))){
    print(paste('### creating folder: ', output_folder_html, ' ###'))
    dir.create(output_folder_html, recursive = TRUE)
  }
  
  if(!(dir.exists(output_folder_json))){
    print(paste('### creating folder: ', output_folder_json, ' ###'))
    dir.create(output_folder_json, recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_path_csv)))){
    print(paste('### creating folder: ', dirname(output_path_csv), ' ###'))
    dir.create(dirname(output_path_csv), recursive = TRUE)
  }
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_path_images, full.names = FALSE, recursive = FALSE)
  
  df_files <- lapply(tmp_folders, function(x){
    tmp_files <- data.frame(ofile = list.files(file.path(input_path_images, x), full.names = FALSE, recursive = FALSE, pattern = '.tif+')) %>% 
      mutate(folder = x)
    return(tmp_files)
  }) %>% bind_rows() %>% 
    mutate(file = sub('.tif+', '', ofile)) %>%
    mutate(file = sub('AF_FITC', 'AFFITC', file)) %>% 
    separate(file, c('slide_id', 'round_number', 'version_id', 'project_id', 'user_id', 'scan_region', 'channel_id'), sep = '_')
  
  # Filter channel
  df_files <- df_files %>% filter(channel_id == ref_channel)
  
  job_list <- data.frame()
  
  for(i in c(1:nrow(df_files))){
    tmp_file <- df_files[i,]
    
    tmp_ref_file <- df_files %>% filter(slide_id == tmp_file$slide_id, scan_region == tmp_file$scan_region, channel_id == ref_channel, round_number == ref_round, version_id == ref_version)
    tmp_job <- data.frame(path_ref_image = file.path(input_path_images, tmp_ref_file$folder, tmp_ref_file$ofile),
                          path_query_image = file.path(input_path_images, tmp_file$folder, tmp_file$ofile),
                          path_model = path_model,
                          path_csv = file.path(output_folder_csv, paste(tmp_file$slide_id, tmp_file$scan_region, sep = '_'), sub('.tiff', '.csv', tmp_file$ofile)),
                          path_html = file.path(output_folder_html, paste(tmp_file$slide_id, tmp_file$scan_region, sep = '_'), sub('.tiff', '.html', tmp_file$ofile)),
                          path_json = file.path(output_folder_json, paste(tmp_file$slide_id, tmp_file$scan_region, sep = '_'), sub('.tiff', '.json', tmp_file$ofile)))
    job_list <- job_list %>% bind_rows(tmp_job)
  }
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Function call ------------------------------------------------------------------
ALGNQCJobList(input_path_images = argv$input_path_images, # Path to input images (dir). Example: /path/to/project_directory/output_registration/output_registration
              output_folder_csv = argv$output_folder_csv, # Path to output path to save csv (dir). Example: /path/to/project_directory/output_registration_qc/csv
              output_folder_html = argv$output_folder_html, # Path to output path to save csv (dir). Example: /path/to/project_directory/output_registration_qc/html
              output_folder_json = argv$output_folder_json, # Path to output path to save csv (dir). Example: /path/to/project_directory/output_registration_qc/json
              path_model = argv$path_model, # Experimental design for the rounds (h5). Example: /src/05_reg_COLLAGE/classification_network.h5
              ref_round = argv$ref_round, # Reference round (str). Example: R01
              ref_version = argv$ref_version, # Reference version (str). Example: V01
              ref_channel = argv$ref_channel, # Reference channel (str). Example: DAPI
              output_path_csv = argv$output_path_csv # Path to output csv where to save the joblist (.csv). Example: /path/to/project_directory/algnqc_job_list.csv
)
