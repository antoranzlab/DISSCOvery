#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Coarse registration from hard stitched images - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_images",
                           help = "Path to input images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_images",
                           help = "Path to output path to save images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_tm",
                           help = "Path to output path to save transformation matrices (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_channel",
                           help = "Reference channel (string).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_round",
                           help = "Reference round (string).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--ref_version",
                           help = "Reference version (string).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

CoarseRegistrationJobList <- function(input_path_images, # Path to input images (path).
                                      output_path_images, # Path to output path to save images (path).
                                      output_path_tm, # Path to output path to save transformation matrices (path).
                                      ref_channel, # Reference channel
                                      ref_round, # Reference round
                                      ref_version, # Reference version
                                      output_path_csv # Path to output csv where the job list will be saved (.csv).
                                 
){
  print(paste0('### input path images: ', input_path_images, ' ###')) 
  print(paste0('### output path images: ', output_path_images, ' ###')) 
  print(paste0('### output path transformation matrices: ', output_path_tm, ' ###')) 
  print(paste0('### reference channel: ', ref_channel, ' ###')) 
  print(paste0('### reference round: ', ref_round, ' ###')) 
  print(paste0('### reference version: ', ref_version, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 
  
  if(!(dir.exists(output_path_images))){
    print(paste('### creating folder: ', output_path_images, ' ###'))
    dir.create(output_path_images, recursive = TRUE)
  }
  
  if(!(dir.exists(output_path_tm))){
    print(paste('### creating folder: ', output_path_tm, ' ###'))
    dir.create(output_path_tm, recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_path_csv)))){
    print(paste('### creating folder: ', dirname(output_path_csv), ' ###'))
    dir.create(dirname(output_path_csv), recursive = TRUE)
  }
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_path_images, full.names = FALSE, recursive = FALSE)
  # tmp_folders <- ''
  df_files <- lapply(tmp_folders, function(x){
    tmp_files <- data.frame(ofile = list.files(file.path(input_path_images, x), full.names = FALSE, recursive = FALSE, pattern = '.tif+')) %>% 
      mutate(folder = x)
    return(tmp_files)
  }) %>% bind_rows() %>% 
    mutate(file = sub('.tif+', '', ofile)) %>% 
    mutate(file = sub('AF_FITC', 'AFFITC', file)) %>% 
    separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_')
  
  df_files <- df_files %>% filter(channel_id == ref_channel)
  
  ref_files <- df_files %>% filter(round_id == ref_round, version_id == ref_version)
  
  job_list <- data.frame()
  for(i in unique(ref_files$slide_id)){
    tmp_ref_file <- ref_files %>% filter(slide_id == i)
    if(nrow(tmp_ref_file) > 1) break('unique reference not found')
    tmp_query_files <- df_files %>% filter(slide_id == i)
    tmp_job_list <- data.frame(fixed_image = file.path(input_path_images, tmp_ref_file$folder, tmp_ref_file$ofile),
                               query_image = file.path(input_path_images, tmp_query_files$folder, tmp_query_files$ofile),
                               output_image = file.path(output_path_images, tmp_query_files$folder, tmp_query_files$ofile),
                               output_tm = file.path(output_path_tm, tmp_query_files$folder, sub('.tiff', '.npy', tmp_query_files$ofile)))
    job_list <- job_list %>% bind_rows(tmp_job_list)
  }
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_images", "output_path_images", "output_path_tm", "ref_channel", "ref_round", "ref_version", "output_path_csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
CoarseRegistrationJobList(input_path_images = argv$input_path_images, # Path to input images (path), example: /path/to/project_directory/hard_stitching
                          output_path_images = argv$output_path_images, # Path to output path to save images (path), example: /path/to/project_directory/output_coarse_registration/images
                          output_path_tm = argv$output_path_tm, # Path to output path to save transformation matrices (path), example: /path/to/project_directory/output_coarse_registration/tm
                          ref_channel = argv$ref_channel, # Ref channel, example: DAPI
                          ref_round = argv$ref_round, # Reference round, example: R01
                          ref_version = argv$ref_version, # Reference version, example: V01
                          output_path_csv = argv$output_path_csv # Path to output csv where the job list will be saved (.csv), example: /path/to/project_directory/coarse_registration_job_list.csv
)
