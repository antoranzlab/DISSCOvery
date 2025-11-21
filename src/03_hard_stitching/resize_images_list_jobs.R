#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse, quietly = TRUE)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Resize images - list jobs.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_images",
                           help = "Path to input tiles (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_folder",
                           help = "Path to output path to save images (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_pixel_size",
                           help = "Pixel size of the input images (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_pixel_size",
                           help = "Desired pixel size for the output images (numeric).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_csv",
                           help = "Path to output csv where the job list will be saved (.csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

ResizeImagesJobList <- function(input_path_images, # Path to input images (path).
                                output_folder, # Path to output path to save images (path).
                                input_pixel_size, # Pixel size input images
                                output_pixel_size, # Pixel size output images
                                output_path_csv # Path to output csv where the job list will be saved (.csv).
                                
){
  print(paste0('### input path images: ', input_path_images, ' ###')) 
  print(paste0('### output directory: ', output_folder, ' ###')) 
  print(paste0('### input pixel size: ', input_pixel_size, ' ###')) 
  print(paste0('### output pixel size: ', output_pixel_size, ' ###')) 
  print(paste0('### output path csv job list: ', output_path_csv, ' ###')) 

  
  input_pixel_size <- as.numeric(input_pixel_size)
  output_pixel_size <- as.numeric(output_pixel_size)
  conversion_factor <- output_pixel_size/input_pixel_size
  
  if(!(dir.exists(output_folder))){
    print(paste('### creating folder: ', output_folder, ' ###'))
    dir.create(output_folder, recursive = TRUE)
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
    separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'), sep = '_', extra = )
  
  job_list <- df_files %>% 
    mutate(input_path_image = file.path(input_path_images, folder, ofile),
           output_path_image = file.path(output_folder, slide_id, ofile),
           conversion_factor = conversion_factor) %>% 
    select(input_path_image, output_path_image, conversion_factor)
  
  write.csv(job_list, output_path_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_images", "output_folder", "input_pixel_size", "output_pixel_size", "output_path_csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
ResizeImagesJobList(input_path_images = argv$input_path_images, # Path to input tiles (dir). Example:  path/to/project_directory/output_processed
                    output_folder = argv$output_folder, # Path to output path to save images (dir). Example:  path/to/project_directory/hard_stitching
                    input_pixel_size = argv$input_pixel_size, # Pixel size input images (numeric). Example: 0.17, 0.5 or 0.28
                    output_pixel_size = argv$output_pixel_size, # Pixel size input images (numeric). Example: 2.6 or 0.65
                    output_path_csv = argv$output_path_csv # Path to output csv where the job list will be saved (.csv). Example:  path/to/project_directory/resize_images_job_list.csv
)


