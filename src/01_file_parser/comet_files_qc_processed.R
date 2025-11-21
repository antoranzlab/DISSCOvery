#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse)
library(argparser, quietly = TRUE)
library(XML)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("QC input files - COMET.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path",
                           help = "Path to input directory with the raw data (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_txt",
                           help = "Path to output file where the experimental design for the rounds will be saved (csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# Auxiliary functions ------------------------------------------------------------------
extract_cycle_info <- function(cycle_node, cycle_num){
  channel_metas <- xpathApply(cycle_node, ".//ChannelMeta")
  tmp_df <- data.frame()
  for(channel_meta in channel_metas){
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
qc_input_files_comet <- function(input_path, # Path to input directory with the raw data (path).
                                 output_txt # Path to output file where theqc report will be stored (txt).
){
  print(paste0('### input path raw data: ', input_path, ' ###')) 
  print(paste0('### output path qc report (txt): ', output_txt, ' ###')) 
  
  if(!(dir.exists(dirname(output_txt)))){
    print(paste('### creating folder: ', dirname(output_txt), ' ###'))
    dir.create(dirname(output_txt), recursive = TRUE)
  }
  
  ## List folders (slides)
  tmp_folders <- list.dirs(input_path, full.names = FALSE, recursive = FALSE) # each folder should correspond to a slide
  
  ## Check1: The .xml jobfile exists for all slides
  df_check1 <- data.frame()
  for(i in tmp_folders){
    tmp_xml_file <- list.files(file.path(input_path, i), pattern = '.xml')
    if(length(tmp_xml_file) == 0) tmp_xml_file <- 'the file does not exist'
    df_check1 <- df_check1 %>% bind_rows(data.frame(folder = i, xml_file = tmp_xml_file))
  }
  
  bad_qc <- df_check1 %>% filter(xml_file == 'the file does not exist')
  if(nrow(bad_qc) > 0){
    message <- paste0('Check1 - xml file QC: NOT PASSED.\nCondition: xml file not found: ', paste(bad_qc$folder, collapse = ".\n"))
    write(message, file = output_txt)
  } else {
    message <- "Check1 - xml file QC: PASSED.\n"
  }
  
  ## Tabulate metadata
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
  
  ## Check2: The ometiff exists
  df_check2 <- data.frame()
  for(i in tmp_folders){
    tiff_name <- list.files(file.path(input_path, i), pattern = '.tiff')
    tmp_qc <- length(tiff_name) == 1
    df_check2 <- df_check2 %>% bind_rows(data.frame(folder = i, file_name = paste(tiff_name, sep = ', ', collapse = ''), QC_tiff = tmp_qc))
  }
  
  bad_qc <- df_check2 %>% filter(QC_tiff == FALSE)
  if(nrow(bad_qc) > 0){
    message <- paste0(message, 'Check2 - ome.tiff file QC: NOT PASSED.\nCondition: number of files found different from 1: ', paste(bad_qc$folder, collapse = ".\n"))
    write(message, file = output_txt)
  } else {
    message <- paste0(message, "Check2 - ome.tiff file QC: PASSED.\n")
  }
  
  ## Check3: Number of cycles per slide
  df_check3 <- df_metadata %>% group_by(folder) %>% summarise(N_cycles = n_distinct(cycle_number)) %>% ungroup()
  qc_cycles <- n_distinct(df_check3$N_cycles)
  if(qc_cycles != 1){
    most_common <- df_check3 %>% group_by(N_cycles) %>% summarise(N = n()) %>% ungroup() %>% filter(N == max(N))
    bad_qc <- df_check3 %>% filter(N_cycles != most_common$N_cycles)
    message <- paste0(message, 'Check3 - Number of cycles per slide QC: NOT PASSED.\nCondition: cycles different from ', most_common$N_cycles, ': ', paste(bad_qc$folder, collapse = ".\n"))
    write(message, file = output_txt)
  } else {
    message <- paste0(message, "Check3 - Number of cycles per slide QC: PASSED.\n")
  }
  
  ## Check4: Cycle folder nomenclature
  # bad_qc <- df_check2 %>% filter(QC_cycle_name == FALSE)
  bad_qc <- df_check2 %>% filter(QC_tiff == FALSE)
  if(nrow(bad_qc) > 0){
    message <- paste0(message, 'Check4 - Cycle folder nomenclature QC: NOT PASSED.\nCondition: cycle folder name non standard: ', paste(bad_qc$folder, collapse = ".\n"))
    write(message, file = output_txt)
  } else {
    message <- paste0(message, "Check4 - Cycle folder nomenclature QC: PASSED.\n")
  }
  
  # ## list files
  # df_files <- lapply(tmp_folders, function(x){
  #   # tmp_directory <- list.dirs(file.path(input_path, x), full.names = FALSE, recursive = FALSE)
  #   # tmp_cycles <- list.dirs(file.path(input_path, x, tmp_directory), full.names = FALSE, recursive = FALSE)
  #   # tmp_files <- lapply(tmp_cycles, function(y){
  #     # tmp_files <- lapply(x, function(y){
  #     # tmp_tiffs <- data.frame(ofile = list.files(file.path(input_path, x, tmp_directory, y), full.names = FALSE, recursive = FALSE, pattern = '.tiff')) %>% 
  #       tmp_tiffs <- data.frame(ofile = list.files(file.path(input_path, x), full.names = FALSE, recursive = FALSE, pattern = '.tiff')) %>% 
  #       mutate(folder = x)
  #     return(tmp_tiffs)
  #   }) %>% bind_rows()
  # #   return(tmp_files)
  # # }) %>% bind_rows()
  # 
  # ## Check5: tiff file nomenclature
  # # df_check5 <- df_files %>% 
  # #   mutate(QC_tiff_file = str_count(ofile, "_"))
  # 
  # # bad_qc <- df_check5 %>% filter(QC_tiff_file != 7)
  # # if(nrow(bad_qc) > 1){
  # #   message <- paste0(message, 'Check5 - Tiff file nomenclature QC: NOT PASSED.\nCondition: cycles different from: ', paste(unique(bad_qc$folder), collapse = ".\n"))
  # #   write(message, file = output_txt)
  # # } else {
  # #   message <- paste0(message, "Check5 - Tiff file nomenclature QC: PASSED.\n")
  # # }
  
  # ## Tabulate filenames
  # df_files <- df_files %>% 
  #   mutate(file = sub('.tif+', '', ofile)) %>% 
  #   separate(file, c('channel', 'channel_name', 'slice', 'slice_id', 'row', 'row_id', 'col', 'col_id'), sep = '_')
  # 
  # ## Check6: channel names are numeric and equal to values in dictionary
  # valid_values <- c("1", "2", "3")
  # df_check6 <-  all(unique(df_files$channel_name) %in% valid_values) && all(valid_values %in% unique(df_files$channel_name))
  # if(df_check6 == FALSE){
  #   bad_qc <- df_files %>% filter(!(channel_name %in% c('1', '2', '3')))
  #   message <- paste0(message, 'Check6 - Channel names QC: NOT PASSED.\nCondition: channel names different: ', paste(unique(bad_qc$folder), collapse = ".\n"))
  #   write(message, file = output_txt)
  # } else {
  #   message <- paste0(message, "Check6 - Channel names QC: PASSED.\n")
  # }
  # 
  # df_files <- df_files %>% 
  #   mutate(channel_name = as.numeric(channel_name)) %>% 
  #   mutate(channel_name = plyr::mapvalues(channel_name, from = c(1:3), to = c('Cy5', 'DAPI', 'TRITC'))) %>% # hardcoded
  #   mutate(cycle_number = sub('Cycle_', '', cycle_id))
  
  # ## Check7: match files and metadata
  # df_check7 <- df_files %>% select(folder, channel_name, cycle_number) %>% unique() %>% mutate(QC_files = TRUE) %>% 
  #   full_join(df_metadata %>% select(folder, FluorescenceChannel, cycle_number) %>% rename(channel_name = FluorescenceChannel) %>% mutate(QC_meta = TRUE))
  # bad_qc <- df_check7 %>% filter(is.na(QC_files))
  # if(nrow(bad_qc) > 0){
  #   message <- paste0(message, 'Check7.a - Matching metadata and files QC: NOT PASSED.\nCondition: missing files in: ', paste(unique(bad_qc$folder), collapse = ".\n"))
  #   write(message, file = output_txt)
  # } else {
  #   message <- paste0(message, "Check7.a - Matching metadata and files QC: PASSED.\n")
  # }
  # bad_qc <- df_check7 %>% filter(is.na(QC_meta))
  # if(nrow(bad_qc) > 0){
  #   message <- paste0(message, 'Check7.b - Matching files and metadata QC: WARNING.\nCondition: missing metadata in: ', paste(unique(bad_qc$folder), collapse = ".\n"))
  # } else {
  #   message <- paste0(message, "Check7.b - Matching files and metadata QC: PASSED.\n")
  # }
  write(message, file = output_txt)
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path", "output_txt")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
qc_input_files_comet(input_path = argv$input_path, # Path to input directory with the raw data (path). Example: /path/to/input_data_files_folder
                     output_txt = argv$output_txt # Path to output file where the qc report will be saved (txt). Example: /path/to/project_directory/qc_input_files.txt
)
