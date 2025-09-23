#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Rename Round Versions.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_tiles",
                           help = "Path to input tiles (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_path_dictionary",
                           help = "Path to output directory (csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

RenameRoundVersions <- function(input_path_tiles, # Path to input tiles (path).
                                output_path_dictionary # Path to output csv to save dictionary (csv).
){
  print(paste0('### input path tiles: ', input_path_tiles, ' ###')) 
  print(paste0('### output path dictionary: ', output_path_dictionary, ' ###')) 
  
  if(!(dir.exists(dirname(output_path_dictionary)))){
    print(paste('### creating folder: ', dirname(output_path_dictionary), ' ###'))
    dir.create(dirname(output_path_dictionary), recursive = TRUE)
  }
  
  df_folders <- data.frame(ofolder = list.dirs(input_path_tiles, full.names = FALSE, recursive = FALSE)) %>% 
    mutate(folder = ofolder) %>% 
    separate(folder, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region'), sep = '_') %>% 
    mutate(old_iter = paste(round_id, version_id, sep = '_')) %>% 
    mutate(new_iter = paste0('R', str_pad(string = plyr::mapvalues(old_iter, from = sort(unique(old_iter)), to = 1:n_distinct(old_iter)), pad = '0', width = 2))) %>% 
    mutate(new_folder_name = paste(slide_id, new_iter, 'V01', project_id, user_id, scan_region, sep = '_'))
  
  tmp_dictionary <- df_folders %>% select(old_iter, new_iter) %>% unique()
  write.csv(tmp_dictionary, output_path_dictionary, row.names = FALSE)
  
  for(i in rev(sort(unique(df_folders$new_iter)))){
    print(i)
    tmp_folders <- df_folders %>% filter(new_iter == i)
    for(j in unique(tmp_folders$ofolder)){
      ## Rename tiff files
      tmp_tiff_files <- data.frame(ofile = list.files(file.path(input_path_tiles, j), full.names = FALSE, recursive = FALSE, pattern = '.tiff')) %>% 
        mutate(ofolder = j) %>% 
        mutate(file = sub('.tiff', '', ofile)) %>% 
        separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region', 'channel_id'), sep = '_') %>% 
        mutate(new_file_name = paste(slide_id, i, 'V01', project_id, user_id, scan_region, paste0(channel_id, '.tiff'), sep = '_'))
      
      for(k in c(1:nrow(tmp_tiff_files))){
        tmp_file <- tmp_tiff_files[k,]
        file.rename(from = file.path(input_path_tiles, j, tmp_file$ofile), 
                    to = file.path(input_path_tiles, j, tmp_file$new_file_name))
      }
      
      ## Rename and adapt csv file
      tmp_csv_files <- data.frame(ofile = list.files(file.path(input_path_tiles, j), full.names = FALSE, recursive = FALSE, pattern = '.csv')) %>% 
        mutate(ofolder = j) %>% 
        mutate(file = sub('.csv', '', ofile)) %>% 
        separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region', 'meta'), sep = '_') %>% 
        mutate(new_file_name = paste(slide_id, i, 'V01', project_id, user_id, paste0(scan_region, '.csv'), sep = '_'))
      if(nrow(tmp_csv_files) > 1) asdasdasd 
      tmp_csv <- read.csv(file.path(input_path_tiles, j, tmp_csv_files$ofile)) %>% 
        mutate(file = sub('.tiff', '', tile_filename)) %>% 
        separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'scan_region', 'channel_id'), sep = '_') %>% 
        mutate(new_tile_filename = paste(slide_id, i, 'V01', project_id, user_id, scan_region, paste0(channel_id, '.tiff'), sep = '_')) %>% 
        select(AcquisitionTime:ValidBitsPerPixel, new_tile_filename) %>% 
        rename(tile_filename = new_tile_filename)
      write.csv(tmp_csv, file.path(input_path_tiles, j, tmp_csv_files$ofile), row.names = FALSE)
      file.rename(from = file.path(input_path_tiles, j, tmp_csv_files$ofile), 
                  to = file.path(input_path_tiles, j, tmp_csv_files$new_file_name))
      
      ## Rename folder
      tmp_feats <- strsplit(j, split = '_')[[1]]
      new_folder_name <- paste(tmp_feats[1], i, 'V01', tmp_feats[4], tmp_feats[5], tmp_feats[6], sep = '_')
      file.rename(from = file.path(input_path_tiles, j), to = file.path(input_path_tiles, new_folder_name))
    }
  }
}   


# Parser check -------------------------------------------------------------------
required_args <- c("input_path_tiles", "output_path_dictionary")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]


if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
RenameRoundVersions(input_path_tiles = argv$input_path_tiles, # Path to input tiles (dir). Example: /path/to/project_directory/split_scenes
                    output_path_dictionary = argv$output_path_dictionary # Path to output dictionary csv (.csv). Example: /path/to/project_directory/round_version_dictionary.csv
)
