#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------
renv::activate()
# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

library(tidyverse)
# library(EBImage)  
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Generate csv fro czi extraction.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.folder",
                           help = "Path to input folder with corrected tiles (directory).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.channel.dictionary",
                           help = "Path to input csv with channel names (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to output folder with corrected tiles (directory).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.csv",
                           help = "Path to output folder where the selected versions will be located.",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

generate_csv_czi_extraction <- function(input_folder, # Path to input czi files (directory).
                                        input_channel_dictionary, # Path to input csv with channel names (csv).
                                        output_folder, # Path to output folder where raw tiles will be stored.
                                        output_csv # Path to output auxiliary csv (csv).
){
  print(paste0('### input folder: ', input_folder, ' ###')) 
  print(paste0('### input channel dictionary: ', input_channel_dictionary, ' ###')) 
  print(paste0('### output folder: ', output_folder, ' ###')) 
  print(paste0('### output csv: ', output_csv, ' ###')) 
  
  # Create folders ------------------------------------------------------------------
  
  # Create output folder for .till files
  if(!(dir.exists(output_folder))){
    print(paste('### creating folder: ', output_folder, ' ###'))
    dir.create(output_folder, recursive = TRUE)
  }
  
  # Create output folder for .csv file
  if(!(dir.exists(dirname(output_csv)))){
    print(paste('### creating folder: ', dirname(output_csv), ' ###'))
    dir.create(dirname(output_csv), recursive = TRUE)
  }
  
  # List files ------------------------------------------------------------------
  
  print('Listing files')
  
  tmp_files <- data.frame(input_path = list.files(input_folder, full.names = TRUE, recursive = TRUE, pattern = '.czi')) %>% 
    mutate(czi_id = sub('.czi', '', basename(input_path))) %>% 
    mutate(output_folder = file.path(output_folder, czi_id)) %>% 
    select(-czi_id) %>% 
    mutate(input_channel_dictionary = input_channel_dictionary)
  
  # Generate csv ------------------------------------------------------------------
  
  tmp_files <- tmp_files %>% 
    mutate(folder = basename(output_folder)) %>% 
    separate(folder, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id'), sep = '_')
  tmp_files <- tmp_files %>% 
    filter(round_id %in% c('R01', 'R02', 'R03', 'R04'))
  print('Creating csv file')
  
  write.csv(tmp_files, output_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("path.input.folder", "path.input.channel.dictionary", "path.output.folder", "path.output.csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
generate_csv_czi_extraction(input_folder = argv$path.input.folder, # Path to input czi files (directory). Example: /path/to/data_files
                            input_channel_dictionary = argv$path.input.channel.dictionary, # Path to input csv with channel names (csv). Example: /path/to/project_directory/channel_names.csv
                            output_folder = argv$path.output.folder, # Path to output raw tiles (directory). Example: /path/to/project_directory/output_tiles_tiff
                            output_csv = argv$path.output.csv # Path to output csv (csv). Example: /path/to/project_directory/output_tiles_tiff/czi_extraction_csv.csv
)

