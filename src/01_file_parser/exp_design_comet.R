#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse)
library(argparser, quietly = TRUE)
library(XML)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Generate the experimental design for COMET.")

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

# Auxiliary functions ------------------------------------------------------------------
extract_cycle_info <- function(cycle_node, cycle_num) {
  channel_metas <- xpathApply(cycle_node, ".//ChannelMeta")
  tmp_df <- data.frame()
  for (channel_meta in channel_metas) {
    channel <- xmlAttrs(xpathApply(channel_meta, ".//Channel")[[1]])
    plane <- xmlAttrs(xpathApply(channel_meta, ".//Plane")[[1]])
    channel_priv <- xmlAttrs(xpathApply(channel_meta, ".//ChannelPriv")[[1]])
    
    # Combine data into a data frame
    tmp_df <- tmp_df %>% bind_rows(data.frame(
      cycle_number = cycle_num,
      channel_name = channel["Name"],
      samples_per_pixel = channel["SamplesPerPixel"],
      color = ifelse(is.null(channel["Color"]), NA, channel["Color"]),
      exposure_time = plane["ExposureTime"],
      exposure_time_unit = plane["ExposureTimeUnit"],
      TheC = plane["TheC"],
      TheT = plane["TheT"],
      TheZ = plane["TheZ"],
      FluorescenceChannel = channel_priv["FluorescenceChannel"],
      LedCurrentUnit = channel_priv["LedCurrentUnit"],
      stringsAsFactors = FALSE))
  }
  return(tmp_df)
}

# Obtain experimental design comet function ------------------------------------------------------------------
exp_design_comet <- function(input_path, # Path to input directory with the raw data (path).
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
    tmp_xml_file <- list.files(file.path(input_path, i), pattern = '.xml')
    xml_data <- xmlParse(file.path(input_path, i, tmp_xml_file))
    
    # Iterate through each CycleModels node and extract information
    cycles <- getNodeSet(xml_data, "//CycleModels")
    for (j in seq_along(cycles)) {
      cycle_path <- xmlGetAttr(cycles[[j]], "TileFolderPath")
      cycle_num <- sub('\\\\$', '', cycle_path)
      cycle_num <- sub('.+\\\\Cycle_', '', cycle_num)
      tmp_df <- extract_cycle_info(cycles[[j]], cycle_num)
      df_metadata <- df_metadata %>% bind_rows(tmp_df %>% mutate(folder = i))
    }
  }
  
  df_exp_design_rounds <- df_metadata %>% 
    select(folder, cycle_number, FluorescenceChannel, channel_name) %>% 
    unique() %>% 
    rename(round_number = cycle_number, channel_id = FluorescenceChannel, marker_name = channel_name) %>% 
    mutate(round_number = as.numeric(round_number)) 
  
  ## the baselines will be the elution rounds after the 
  ref_rounds_af <- df_exp_design_rounds %>% 
    filter(channel_id != 'DAPI') %>%
    filter(marker_name == channel_id) %>% 
    select(folder, round_number) %>% 
    unique()
  
  ref_rounds_markers <- df_exp_design_rounds %>% 
    filter(marker_name != channel_id) %>% 
    select(folder, round_number) %>% 
    unique() 
  
  af_round_dict <- data.frame()
  for(tmp_marker_round in c(1:nrow(ref_rounds_markers))){
    tmp_row <- ref_rounds_markers[tmp_marker_round,]
    tmp_delta <- ref_rounds_af %>% filter(folder == tmp_row$folder) %>% mutate(tmp_delta = abs(round_number - tmp_row$round_number)) %>% filter(tmp_delta == min(tmp_delta)) %>% 
      filter(round_number == max(round_number))
    tmp_row$ref_round_af <- tmp_delta$round_number
    af_round_dict <- af_round_dict %>% bind_rows(tmp_row)
  }
  
  df_exp_design_rounds <- df_exp_design_rounds %>% 
    left_join(af_round_dict) %>% 
    mutate(ref_round_af = ifelse(is.na(ref_round_af), round_number, ref_round_af)) %>% 
    mutate(round_number = paste0('R', str_pad(round_number, width = 2, pad = '0'))) %>% 
    mutate(ref_round_af = paste0('R', str_pad(ref_round_af, width = 2, pad = '0'))) %>% 
    mutate(QC_include = 1) %>%
    mutate(marker_id=marker_name) # Duplication, remove later if nt necessary
    
  write.csv(df_exp_design_rounds, exp_design_rounds, row.names = FALSE)
  
  df_exp_design_slides <- df_metadata %>% 
    select(folder) %>% 
    unique()
  
  write.csv(df_exp_design_slides, exp_design_slides, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path", "exp_design_rounds", "exp_design_slides")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
exp_design_comet(input_path = argv$input_path, # Path to input directory with the raw data (path). Example: /path/to/input_data_files_folder
                 exp_design_rounds = argv$exp_design_rounds, # Path to output file where the experimental design for the rounds will be saved (csv). Example: /path/to/project_directory/experimental_design/exp_design_rounds.csv
                 exp_design_slides = argv$exp_design_slides # Path to the output file where the experimental design for the slides will be saved (csv). Example: /path/to/project_directory/experimental_design/exp_design_slides.csv
)
