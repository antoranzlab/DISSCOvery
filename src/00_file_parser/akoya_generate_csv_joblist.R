#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

library(tidyverse)
library(EBImage)  
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Generate csv for data extraction extraction.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.folder",
                           help = "Path to the main project folder (directory).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.folder",
                           help = "Path to output folder where to save (directory).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.input.slide.dictionary",
                           help = "Path to input csv with slide dictionary (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.exp.design.rounds.file",
                           help = "Path to input csv with the experimental design for the rounds (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--user.id",
                           help = "Identifier for the user.",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--project.id",
                           help = "Identifier for the project.",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path.output.csv",
                           help = "Path to the output csv where to save the list of jobs (csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

generate_csv_image_extraction <- function(input_folder, # Path to input project folder (folder).
                                          output_folder, # Path to output directory to save the data (folder).
                                          input_slide_dictionary, # Path to input csv with the dictionary for the slide dictionary (csv).
                                          exp_design_rounds_file, # Path to input csv with the experimental design for the rounds (csv).
                                          user_id, # Identifier for the user.
                                          project_id, # Identifier for the project.
                                          output_csv # Path to output csv with list of jobs (csv).
){
  print(paste0('### input folder: ', input_folder, ' ###')) 
  print(paste0('### output folder: ', output_folder, ' ###')) 
  print(paste0('### input channel dictionary: ', input_slide_dictionary, ' ###')) 
  print(paste0('### experimental design rounds: ', exp_design_rounds_file, ' ###')) 
  print(paste0('### user identifier: ', user_id, ' ###')) 
  print(paste0('### project identifier: ', project_id, ' ###')) 
  print(paste0('### output csv: ', output_csv, ' ###')) 

  
  if(!(dir.exists(output_folder))){
    print(paste('### creating folder: ', output_folder, ' ###'))
    dir.create(output_folder, recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_csv)))){
    print(paste('### creating folder: ', dirname(output_csv), ' ###'))
    dir.create(dirname(output_csv), recursive = TRUE)
  }
  
  # List files ------------------------------------------------------------------
  
  print('Listing files')
  
  tmp_folders <- data.frame(input_path = list.dirs(input_folder, full.names = TRUE, recursive = FALSE)) %>% 
    mutate(output_folder = output_folder) %>% 
    mutate(project_id = project_id) %>% 
    mutate(user_id = user_id) %>% 
    mutate(input_slide_dictionary = input_slide_dictionary) %>% 
    mutate(exp_design_rounds_file = exp_design_rounds_file)


  # Generate csv ------------------------------------------------------------------
  
  print('Creating csv file')
  
  write.csv(tmp_folders, output_csv, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("path.input.folder", "path.output.folder", "path.input.slide.dictionary", "path.exp.design.rounds.file", "user.id", "project.id", "path.output.csv")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
generate_csv_image_extraction(input_folder = argv$path.input.folder, # Path to input files (dir). Example: /path/to/data_files
                              output_folder = argv$path.output.folder, # Path to output tiles (dir). Example: /path/to/project_directory/output_tiles_tiffs
                              input_slide_dictionary = argv$path.input.slide.dictionary, # Path to input csv with slide names (csv). Example: /path/to/project_directory/experimental_design/exp_design_slides.csv
                              exp_design_rounds_file = argv$path.exp.design.rounds.file, # Path to experimental design file rounds (csv). Example: /path/to/project_directory/experimental_design/exp_design_rounds.csv
                              user_id = argv$user.id, # User identifier (str). Example: JM
                              project_id = argv$project.id, # Project identifier (str). Example: PROJECT_COMET
                              output_csv = argv$path.output.csv # Path to output csv (csv). Example: /path/to/project_directory/data_parsing.csv
)
