#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Generation of bounding boxes - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_images",
                           help = "Path to input images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_bbs",
                           help = "Path to output path to save the csv (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--filter_small",
                           help = "Boolean to filter small objects or not (boolean).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

BBEstimationJobList <- function(input_path_images, # Path to input images (path).
                                output_path_bbs, # Path to output path to save csv (path).
                                filter_small, # Boolean to filter small objects.
                                output_path_csv # Path to output csv where the job list will be saved (.csv).
                                 
){
  print(paste0('### input path images: ', input_path_images, ' ###')) 
  print(paste0('### output path bounding boxes: ', output_path_bbs, ' ###')) 
  print(paste0('### filter small objects: ', filter_small, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 
  
  if(!(dir.exists(output_path_bbs))){
    print(paste('### creating folder: ', output_path_bbs, ' ###'))
    dir.create(output_path_bbs, recursive = TRUE)
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
    separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_')
  
  job_list <- df_files %>% 
    mutate(input_image = file.path(input_path_images, folder, ofile),
           output_bb = file.path(output_path_bbs, folder, sub('.tiff', '.csv', ofile)),
           filter_small = filter_small) %>% 
    select(input_image, output_bb, filter_small)
  
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_images", "output_path_bbs", "filter_small", "output_path_csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
BBEstimationJobList(input_path_images = argv$input_path_images, # Path to input images (path), example: /path/to/project_directory/output_STS/output_masks
                    output_path_bbs = argv$output_path_bbs, # Path to output path to save csv (path), example: /path/to/project_directory/output_STS/BBs
                    filter_small = argv$filter_small, # Filter small objects, example: True
                    output_path_csv = argv$output_path_csv # Path to output csv where the job list will be saved (.csv), example: /path/to/project_directory/BB_estimation_job_list.csv
)