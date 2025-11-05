#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

# install.packages('https://cran.r-project.org/src/contrib/Archive/ff/ff_2.2-14.tar.gz', repos=NULL)
# https://community.rstudio.com/t/unable-to-install-bioconductor-package/75223

library(tidyverse)
library(EBImage)  
library(data.table)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Parse slide names to exp design rounds.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--path_input_exp_design_rounds",
                           help = "Path to the exp design rounds (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path_input_exp_design_slides",
                           help = "Path to the exp design slides (csv).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--path_output_exp_design_merged",
                           help = "Path to the exp design merged (csv).",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# PostProcessing function ------------------------------------------------------------------

parse_slide_names <- function(path_input_exp_design_rounds, # Path to the exp design rounds (csv).
                              path_input_exp_design_slides, # Path to the exp design slides (csv).
                              path_output_exp_design_merged # Path to the exp design merged (csv).
){
  print(paste0('### path exp design rounds: ', path_input_exp_design_rounds, ' ###')) 
  print(paste0('### path exp design slides: ', path_input_exp_design_slides, ' ###'))
  print(paste0('### path exp design merged: ', path_output_exp_design_merged, ' ###')) 

  if(!(dir.exists(dirname(path_output_exp_design_merged)))){
    print(paste('### creating folder: ', dirname(path_output_exp_design_merged), ' ###'))
    dir.create(dirname(path_output_exp_design_merged), recursive = TRUE)
  }
  
  # read files ------------------------------------------------------------------
  
  print('Reading files')
  
  tmp_exp_design_rounds <- fread(path_input_exp_design_rounds, sep = ',')
  tmp_exp_design_slides <- fread(path_input_exp_design_slides, sep = ',')
  
  # Merge files ------------------------------------------------------------------
  
  print('Merging files')
  
  tmp_exp_design_merged <- tmp_exp_design_rounds %>% 
    left_join(tmp_exp_design_slides)
  
  tmp_exp_design_merged <- tmp_exp_design_merged %>% select(-folder)
  
  # Generate csv ------------------------------------------------------------------
  
  print('Creating csv file')
  
  fwrite(tmp_exp_design_merged, path_output_exp_design_merged, row.names = FALSE)
}

# Parser check -------------------------------------------------------------------
required_args <- c("path_input_exp_design_rounds", "path_input_exp_design_slides", "path_output_exp_design_merged")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]

if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}

# Function call ------------------------------------------------------------------
parse_slide_names(path_input_exp_design_rounds = argv$path_input_exp_design_rounds, # Path to input exp design rounds (csv). Example: /path/to/project_directory/experimental_design/exp_design_rounds.csv
                  path_input_exp_design_slides = argv$path_input_exp_design_slides, # Path to input exp design slides (csv). Example: /path/to/project_directory/experimental_design/exp_design_slides.csv
                  path_output_exp_design_merged = argv$path_output_exp_design_merged # Path to the output exp design merged (csv). Example: /path/to/project_directory/experimental_design/exp_design_rounds.csv
)
