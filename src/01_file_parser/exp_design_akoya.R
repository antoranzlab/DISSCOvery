#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse)
library(argparser, quietly = TRUE)
library(jsonlite)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Generate the experimental design for AKOYA - PhenoCycler.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path",
                           help = "Path to input directory with the raw data (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--exp_design_rounds",
                           help = "Path to output file where the experimental design for the rounds will be saved (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--exp_design_slides",
                           help = "Path to the output file where the experimental design for the slides will be saved (csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# Obtain experimental design comet function ------------------------------------------------------------------
exp_design_akoya <- function(input_path, # Path to input directory with the raw data (path).
                             exp_design_rounds, # Path to output file where the experimental design for the rounds will be saved (csv).
                             exp_design_slides # Path to the output file where the experimental design for the slides will be saved (csv).
){
  print(paste0('### input path raw data: ', input_path, ' ###')) 
  print(paste0('### output path experimental design rounds (csv): ', exp_design_rounds, ' ###')) 
  print(paste0('### output path experimental design slides (csv): ', exp_design_slides, ' ###'))
    
  if(!(dir.exists(dirname(exp_design_rounds)))){
    print(paste('### creating folder: ', dirname(exp_design_rounds), ' ###'))
    dir.create(dirname(exp_design_rounds), recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(exp_design_slides)))){
    print(paste('### creating folder: ', dirname(exp_design_slides), ' ###'))
    dir.create(dirname(exp_design_slides), recursive = TRUE)
  }
  
  ## Tabulate data
  tmp_folders <- list.dirs(input_path, full.names = FALSE, recursive = FALSE) # each folder should correspond to a slide
  
  df_metadata <- data.frame()
  for(i in tmp_folders){
    
    tmp_xpd_file <- list.files(file.path(input_path, i), pattern = '.xpd$')
    
    if(length(tmp_xpd_file) != 1) break('metadata file not found.')
    
    # Load the JSON data
    tmp_data <- fromJSON(file.path(input_path, i, tmp_xpd_file))
    
    tmp_resolution <- tmp_data$resolution
    
    # Initialize a list (similar to a Python list) to hold all flattened marker data
    all_markers <- list()
    
    # Process each well and its items
    for(j in c(1:nrow(tmp_data$wells))){
      well_name <- tmp_data$wells[j,]$wellName
      items <- tmp_data$wells[j,]$items[[1]]
      for(k in c(1:nrow(items))){
        item <- items[k,]
        # Extract relevant fields and add well information
        marker_info <- list(
          'well_name' = well_name,
          'marker_name' = item$markerName,
          'marker_id' = item$markerName, # Duplication to make AFS work, remove later on if it won't be necessary anymore
          'channel_id' = item$channel,
          channel_number = k-1
        )
        all_markers <- append(all_markers, list(marker_info))
      }
    }
    
    # Convert the list of lists to a data frame
    tmp_markers <- do.call(rbind, lapply(all_markers, as.data.frame, stringsAsFactors = FALSE)) %>% 
      mutate(folder = i, pixel_size = tmp_resolution)
    
    tmp_markers <- tmp_markers %>% 
      mutate(round_number = plyr::mapvalues(well_name, from = unique(well_name), to = c(1:(n_distinct(well_name))))) %>% 
      mutate(marker_name = ifelse(marker_name == '--', 'AF', marker_name)) %>% 
      mutate(round_number = paste0('R', str_pad(round_number, width = 2, pad = '0'))) %>% 
      mutate(QC_include = 1)
    
    df_metadata <- df_metadata %>% bind_rows(tmp_markers)
  }
  
  df_metadata <- df_metadata %>% mutate(channel_number = plyr::mapvalues(channel_id, from = c('DAPI', 'ATTO550', 'AF750', 'CY5'), to = c(0:3)))
  write.csv(df_metadata, exp_design_rounds, row.names = FALSE)
  
  df_exp_design_slides <- df_metadata %>% 
    select(folder) %>% 
    unique()
  
  write.csv(df_exp_design_slides, exp_design_slides, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path", "input_path", "exp_design_slides")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
exp_design_akoya(input_path = argv$input_path, # Path to input directory with the raw data (path). Example: /path/to/input_data_files_folder
                 exp_design_rounds = argv$exp_design_rounds, # Path to output file where the experimental design for the rounds will be saved (csv). Example: /path/to/project_directory/experimental_design/exp_design_rounds.csv
                 exp_design_slides = argv$exp_design_slides # Path to the output file where the experimental design for the slides will be saved (csv). Example: /path/to/project_directory/experimental_design/exp_design_slides.csv
)