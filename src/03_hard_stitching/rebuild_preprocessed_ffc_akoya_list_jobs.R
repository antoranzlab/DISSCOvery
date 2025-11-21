#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Coarse stitching from individual tiles - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_tiles",
                           help = "Path to input tiles (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_meta",
                           help = "Path to input metadata files (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder",
                           help = "Path to output path to save images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_pixel_size",
                           help = "Pixel size for output images.",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

HardStitchingJobList <- function(input_path_tiles, # Path to input tiles (path).
                                 input_path_meta, # Path to input metadata files (path).
                                 output_folder, # Path to output path to save images (path).
                                 output_path_csv, # Path to output csv where the job list will be saved (.csv).
                                 output_pixel_size # Maximum size of the hard stitching images (numeric).
){
  print(paste0('### input path tiles: ', input_path_tiles, ' ###')) 
  print(paste0('### input path metadata: ', input_path_meta, ' ###')) 
  print(paste0('### output directory: ', output_folder, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 
  print(paste0('### output pixel size: ', output_pixel_size, ' ###')) 


  output_pixel_size <- as.numeric(output_pixel_size)
  
  if(!(dir.exists(output_folder))){
    print(paste('### creating folder: ', output_folder, ' ###'))
    dir.create(output_folder, recursive = TRUE)
  }
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_path_tiles, full.names = FALSE, recursive = FALSE)
  
  df_files <- lapply(tmp_folders, function(x){
    tmp_files <- data.frame(ofile = list.files(file.path(input_path_tiles, x), full.names = FALSE, recursive = FALSE, pattern = '.tif+')) %>% 
      mutate(folder = x)
    return(tmp_files)
  }) %>% bind_rows() %>% 
    mutate(file = sub('.tif+', '', ofile)) %>% 
    mutate(file = sub('AF_FITC', 'AFFITC', file)) %>% 
    separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'mosaic_index', 'channel_id'), sep = '_')
  
  job_list <- data.frame()
  
  ## Tabulate metadata
  for(i in unique(df_files$folder)){
    print(i)
    
    tmp_files <- df_files %>% filter(folder == i)
    
    # if(!(dir.exists(file.path(output_folder, unique(tmp_files$slide_id))))){
    if(!(dir.exists(file.path(output_folder, i)))){
      print(paste('### creating folder: ', file.path(output_folder, i), ' ###'))
      dir.create(file.path(output_folder, i), recursive = TRUE)
    }
    
    tmp_file <- list.files(file.path(input_path_meta, i), full.names = FALSE, recursive = FALSE, pattern = '.csv')
    if(length(tmp_file) != 1) stop('error fetching the metadata')
    
    tmp_csv <- read.csv(file.path(input_path_meta, i, tmp_file), stringsAsFactors = FALSE) %>% 
      group_by(S, M) %>% 
      sample_n(1) %>% 
      ungroup() %>% 
      separate(ImagePixelSize, c('px_size_X', 'px_size_Y'), sep = ',') %>% 
      mutate(px_size_X = as.numeric(px_size_X)/10,
             px_size_Y = as.numeric(px_size_Y)/10) %>% 
      mutate(StageXPosition = StageXPosition/px_size_X) %>% 
      mutate(StageYPosition = StageYPosition/px_size_Y) %>% 
      separate(Frame, c('aux_1', 'aux_2', 'tile_size_X', 'tile_size_Y'), sep = ',') %>% 
      mutate(tile_size_X = as.numeric(tile_size_X),
             tile_size_Y = as.numeric(tile_size_Y)) %>% 
      mutate(tmp_X = StageXPosition - min(StageXPosition) + tile_size_X/2) %>% 
      mutate(tmp_Y = StageYPosition - min(StageYPosition) + tile_size_Y/2) %>% 
      mutate(tile_id = 1:n())
    
    conversion_factor <- output_pixel_size/unique(tmp_csv$px_size_X)
    
    tmp_job <- data.frame(input_path_tiles = file.path(input_path_tiles, i), 
                          input_path_meta = file.path(input_path_meta, i, tmp_file),
                          output_folder = file.path(output_folder, i),
                          conversion_factor = conversion_factor)
    job_list <- job_list %>% bind_rows(tmp_job)
  }
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Function call ------------------------------------------------------------------
HardStitchingJobList(input_path_tiles = argv$input_path_tiles, # Path to input tiles (dir). Example:  path/to/project_directory/output_FFC_corrected
                     input_path_meta = argv$input_path_meta, # Path to input metadata files (dir). Example:  path/to/project_directory/output_FFC_corrected
                     output_folder = argv$output_folder, # Path to output path to save images (dir). Example:  path/to/project_directory/output_processed
                     output_path_csv = argv$output_path_csv, # Path to output csv where the job list will be saved (.csv). Example:  path/to/project_directory/rebuild_processed_job_list.csv
                     output_pixel_size = argv$output_pixel_size # Output pixel size (numeric). Example:  2.6, 0.65 or 0.5
)
