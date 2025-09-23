#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Undo rename Round Versions.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_images_ffc",
                           help = "Path to input images ffc (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_images_reg",
                           help = "Path to input images registration (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_dictionary",
                           help = "Path to output directory (csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

UndoRenameRoundVersions <- function(input_path_images_ffc, # Path to input tiles (path).
                                    input_path_images_reg, # Path to input registered images (path).
                                    input_path_dictionary # Path to output csv to save dictionary (csv).
){
  print(paste0('### input path images FFC: ', input_path_images_ffc, ' ###')) 
  print(paste0('### input path images registration: ', input_path_images_reg, ' ###')) 
  print(paste0('### output path dictionary: ', input_path_dictionary, ' ###'))
  
  tmp_dictionary <- read.csv(input_path_dictionary, stringsAsFactors = FALSE)
  
  ## FFC tiles
  df_folders <- data.frame(ofolder = list.dirs(input_path_images_ffc, full.names = FALSE, recursive = FALSE)) %>% 
    mutate(folder = ofolder) %>% 
    separate(folder, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region'), sep = '_') %>% 
    left_join(tmp_dictionary %>% rename(round_id = new_iter)) %>%
    mutate(new_folder_name = paste(slide_id, old_iter, project_id, user_id, scan_region, sep = '_'))
  
  for(i in (sort(unique(df_folders$ofolder)))){
    print(i)
    tmp_folders <- df_folders %>% filter(ofolder == i)
    ## Rename tiff files
    tmp_tiff_files <- data.frame(ofile = list.files(file.path(input_path_images_ffc, i), full.names = FALSE, recursive = FALSE, pattern = '.tiff')) %>% 
      mutate(ofolder = i) %>% 
      mutate(file = sub('.tiff', '', ofile)) %>% 
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region', 'channel_id'), sep = '_') %>% 
      left_join(tmp_dictionary %>% rename(round_id = new_iter)) %>%
      mutate(new_file_name = paste(slide_id, old_iter, project_id, user_id, scan_region, paste0(channel_id, '.tiff'), sep = '_'))
    
    for(k in c(1:nrow(tmp_tiff_files))){
      tmp_file <- tmp_tiff_files[k,]
      file.rename(from = file.path(input_path_images_ffc, i, tmp_file$ofile), 
                  to = file.path(input_path_images_ffc, i, tmp_file$new_file_name))
    }
    
    ## Rename and adapt csv file
    tmp_csv_files <- data.frame(ofile = list.files(file.path(input_path_images_ffc, i), full.names = FALSE, recursive = FALSE, pattern = '.csv')) %>% 
      mutate(ofolder = i) %>% 
      mutate(file = sub('.csv', '', ofile)) %>% 
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region'), sep = '_') %>% 
      left_join(tmp_dictionary %>% rename(round_id = new_iter)) %>%
      mutate(new_file_name = paste(slide_id, old_iter, project_id, user_id, paste0(scan_region, '.csv'), sep = '_'))
    if(nrow(tmp_csv_files) > 1) asdasdasd
    tmp_csv <- read.csv(file.path(input_path_images_ffc, i, tmp_csv_files$ofile)) %>% 
      mutate(file = sub('.tiff', '', tile_filename)) %>% 
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region', 'channel_id'), sep = '_') %>% 
      left_join(tmp_dictionary %>% rename(round_id = new_iter)) %>%
      mutate(new_tile_filename = paste(slide_id, old_iter, project_id, user_id, scan_region, paste0(channel_id, '.tiff'), sep = '_')) %>% 
      select(AcquisitionTime:ValidBitsPerPixel, new_tile_filename) %>% 
      rename(tile_filename = new_tile_filename)
    write.csv(tmp_csv, file.path(input_path_images_ffc, i, tmp_csv_files$ofile), row.names = FALSE)
    file.rename(from = file.path(input_path_images_ffc, i, tmp_csv_files$ofile), 
                to = file.path(input_path_images_ffc, i, tmp_csv_files$new_file_name))
    
    ## Rename folder
    file.rename(from = file.path(input_path_images_ffc, i), to = file.path(input_path_images_ffc, tmp_folders$new_folder_name))
  }
  
  ## Registration images
  df_folders <- data.frame(ofolder = list.dirs(input_path_images_reg, full.names = FALSE, recursive = FALSE)) %>% 
    mutate(folder = ofolder) %>% 
    separate(folder, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region'), sep = '_') %>% 
    left_join(tmp_dictionary %>% rename(round_id = new_iter)) %>%
    mutate(new_folder_name = paste(slide_id, old_iter, project_id, user_id, scan_region, sep = '_'))
  
  for(i in (sort(unique(df_folders$ofolder)))){
    print(i)
    tmp_folders <- df_folders %>% filter(ofolder == i)
    ## Rename tiff files
    tmp_tiff_files <- data.frame(ofile = list.files(file.path(input_path_images_reg, i), full.names = FALSE, recursive = FALSE, pattern = '.tiff')) %>% 
      mutate(ofolder = i) %>% 
      mutate(file = sub('.tiff', '', ofile)) %>% 
      separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region', 'channel_id'), sep = '_') %>% 
      left_join(tmp_dictionary %>% rename(round_id = new_iter)) %>%
      mutate(new_file_name = paste(slide_id, old_iter, project_id, user_id, scan_region, paste0(channel_id, '.tiff'), sep = '_'))
    
    for(k in c(1:nrow(tmp_tiff_files))){
      tmp_file <- tmp_tiff_files[k,]
      file.rename(from = file.path(input_path_images_reg, i, tmp_file$ofile), 
                  to = file.path(input_path_images_reg, i, tmp_file$new_file_name))
    }
    
    ## Rename folder
    file.rename(from = file.path(input_path_images_reg, i), to = file.path(input_path_images_reg, tmp_folders$new_folder_name))
  }
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_images_ffc", "input_path_images_reg", "input_path_dictionary")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]


if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# # Function call ------------------------------------------------------------------
UndoRenameRoundVersions(input_path_images_ffc = argv$input_path_images_ffc, # Path to input tiles (dir). Example: /path/to/project_directory/output_FFC_corrected
                        input_path_images_reg = argv$input_path_images_reg, # Path to input registration files (dir). Example: /path/to/project_directory/output_registration
                        input_path_dictionary = argv$input_path_dictionary # Path to output dictionary csv (.csv). Example: /path/to/project_directory/round_version_dictionary.csv
)
