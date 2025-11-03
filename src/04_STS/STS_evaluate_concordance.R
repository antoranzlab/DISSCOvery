#!/usr/bin/env Rscript

# Load Packages -----------------------------------------------------------

library(tidyverse)
library(EBImage) 
library(plotly)
library(argparser, quietly = TRUE)

# Parser ------------------------------------------------------------------

tmp_parser <- arg_parser("Evaluate concordance between bounding boxes belonging to the same slide.")

# Add command line arguments
tmp_parser <- add_argument(tmp_parser,
                           arg = "--input_path_BB",
                           help = "Path to input directory with the bounding boxes (path).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_heatmap_path_html",
                           help = "Path to output path where the html plot will be saved (html).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--output_heatmap_path_json",
                           help = "Path to output path where the json plot will be saved (json).",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--reference_round",
                           help = "Identifier for the round used as reference.",
                           type = "character")

tmp_parser <- add_argument(tmp_parser,
                           arg = "--reference_version",
                           help = "Identifier for the version used as reference.",
                           type = "character")

# Parse the command line arguments
argv <- parse_args(tmp_parser)

# Auxiliary functions ------------------------------------------------------------------
calculate_iou_matrix <- function(ref_boxes, query_boxes) {
  # Extract coordinates of the reference and query boxes
  minr_ref <- ref_boxes$minr
  minc_ref <- ref_boxes$minc
  maxr_ref <- ref_boxes$maxr
  maxc_ref <- ref_boxes$maxc
  
  minr_query <- query_boxes$minr
  minc_query <- query_boxes$minc
  maxr_query <- query_boxes$maxr
  maxc_query <- query_boxes$maxc
  
  # Compute the intersection coordinates
  intersect_minr <- outer(minr_ref, minr_query, FUN = pmax)
  intersect_minc <- outer(minc_ref, minc_query, FUN = pmax)
  intersect_maxr <- outer(maxr_ref, maxr_query, FUN = pmin)
  intersect_maxc <- outer(maxc_ref, maxc_query, FUN = pmin)
  
  # Compute intersection areas
  intersect_width <- pmax(0, intersect_maxr - intersect_minr)
  intersect_height <- pmax(0, intersect_maxc - intersect_minc)
  intersection_area <- intersect_width * intersect_height
  
  # Compute areas of the reference and query boxes
  area_ref <- (maxr_ref - minr_ref) * (maxc_ref - minc_ref)
  area_query <- (maxr_query - minr_query) * (maxc_query - minc_query)
  
  # Compute union areas
  union_area <- outer(area_ref, area_query, FUN = "+") - intersection_area
  
  # Compute IoU
  iou_matrix <- intersection_area / union_area
  
  return(iou_matrix)
}

# STS_evaluate_concordance function ------------------------------------------------------------------
STS_evaluate_concordance <- function(input_path_BB, # Path to input directory with the bounding boxes (path).
                                     output_heatmap_path_html, # Path to output path where the html plot will be saved (html).
                                     output_heatmap_path_json, # Path to output path where the json plot will be saved (json).
                                     reference_round, # Identifier for the round used as reference.
                                     reference_version # Identifier for the version used as reference.
){
  print(paste0('### input path bounding boxes: ', input_path_BB, ' ###')) 
  print(paste0('### output heatmap path (html): ', output_heatmap_path_html, ' ###')) 
  print(paste0('### output heatmap path (json): ', output_heatmap_path_json, ' ###')) 
  print(paste0('### reference round: ', reference_round, ' ###')) 
  print(paste0('### reference version: ', reference_version, ' ###')) 

  if(!(dir.exists(dirname(output_heatmap_path_html)))){
    print(paste('### creating folder: ', dirname(output_heatmap_path_html), ' ###'))
    dir.create(dirname(output_heatmap_path_html), recursive = TRUE)
  }
  
  if(!(dir.exists(dirname(output_heatmap_path_json)))){
    print(paste('### creating folder: ', dirname(output_heatmap_path_json), ' ###'))
    dir.create(dirname(output_heatmap_path_json), recursive = TRUE)
  }
  
  ## Tabulate data
  df_files <- data.frame(ofile = list.files(input_path_BB, pattern = '.csv', full.names = FALSE, recursive = FALSE)) %>% 
    mutate(file = sub('.csv', '', ofile)) %>% 
    separate(file, c('slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'channel_id'))
  
  ref_file <- df_files %>% filter(round_id == reference_round, version_id == reference_version)
  if(nrow(ref_file) != 1) stop('reference not found.')
  
  query_files <- df_files %>% setdiff(ref_file)
  
  if(nrow(query_files) < 1) stop('no query files.')
  
  # Load reference objects
  ref_objects <- read.csv(file.path(input_path_BB, ref_file$ofile))
  
  # Evaluate contingency
  contingency_matrix <- lapply(1:nrow(query_files), function(i){
    query_file <- query_files[i,]
    query_objects <- read.csv(file.path(input_path_BB, query_file$ofile))
    
    tmp_iou_matrix <- calculate_iou_matrix(ref_objects, query_objects)
    rownames(tmp_iou_matrix) <- ref_objects$scan_region
    colnames(tmp_iou_matrix) <- query_objects$scan_region
    tmp_df_iou <- reshape::melt(tmp_iou_matrix)
    colnames(tmp_df_iou) <- c('Sref', 'Squery', 'IoU')
    tmp_df_iou$ofile <- query_file$ofile
    return(tmp_df_iou)
  })
  
  contingency_matrix <- do.call(rbind, contingency_matrix)
  
  # For each reference object, choose the best match
  best_match <- contingency_matrix %>% 
    group_by(ofile, Sref) %>% 
    filter(IoU == max(IoU)) %>% 
    ungroup() %>% 
    mutate(ofile = sub('.csv', '', ofile)) %>% 
    mutate(S = as.numeric(sub('S', '', Sref))) %>% 
    arrange(S) %>% 
    mutate(Sref = factor(Sref, levels = unique(Sref))) %>% 
    select(-S)
  
  # Create the interactive heatmap with plotly
  heatmap_plot <- plot_ly(
    data = best_match,
    x = ~Sref,
    y = ~ofile,
    z = ~IoU,
    type = "heatmap",
    colors = colorRamp(c('white', 'indianred')),
    text = ~paste("Squery:", Squery, "<br>IoU:", IoU),
    hoverinfo = 'text'
  ) %>%
    layout(
      title = NULL,  # No title
      xaxis = list(title = "", tickvals = unique(best_match$Sref)),  # Remove x-axis title but keep tick labels
      yaxis = list(title = "", tickvals = unique(best_match$ofile)),  # Remove y-axis title but keep tick labels
      hoverlabel = list(bgcolor = "white")  # Keep hover labels
    )
  
  # Export the plot as an interactive HTML file
  htmlwidgets::saveWidget(heatmap_plot, output_heatmap_path_html)
  
  heatmap_json <- plotly_json(heatmap_plot, jsonedit = FALSE, pretty = TRUE) # important jsonedit = FALSE
  # Save the JSON to a file
  write(heatmap_json, file = sub('.html', '.json', output_heatmap_path_json))
}

# Parser check -------------------------------------------------------------------
required_args <- c("input_path_BB", "output_heatmap_path_html", "output_heatmap_path_json", 
                   "reference_round", "reference_version")
missing_args <- required_args[sapply(required_args, function(x) is.null(argv[[x]]) || is.na(argv[[x]]))]


if (length(missing_args) > 0) {
  cat("Missing required arguments:", paste(missing_args, collapse = ", "), "\n\n")
  print(tmp_parser)
  quit(status = 1)
}


# Function call ------------------------------------------------------------------
STS_evaluate_concordance(input_path_BB = argv$input_path_BB, # Path to input directory with the bounding boxes (dir), example: /path/to/project_directory/output_STS/BBs
                         output_heatmap_path_html = argv$output_heatmap_path_html, # Path to output path where the html plot will be saved (.html), example: /path/to/project_directory/output_STS/heatmaps_html
                         output_heatmap_path_json = argv$output_heatmap_path_json, # Path to output path where the json plot will be saved (.json), example: V01
                         reference_round = argv$reference_round, # Identifier for the round used as reference, example: R01
                         reference_version = argv$reference_version # Identifier for the version used as reference, example: /path/to/project_directory/bb_concordance_job_list.csv
)