<h1 align="center"> Files Preparation </h1>

---

## Table of content

[1. Raw tiles](#1-raw-tiles)

[2. Experimental design](#2-experimental-design)

[3. Data parsing](#3-data-parsing)

<pre> 00_file_parser 
├── MILAN
|    1. czi_files_qc.py
|    2. czi_extract_channel_metadata.py
|    3. run_czi_extraction.py
|         └── czi_reader.py

</pre>


---

## 1. Raw tiles QC

---
 **Script:** [czi_files_qc.py](src/00_file_parser/czi_files_qc.py)


### Description
The script ensures the correctness of the input data. It checks if:

- All detected files are .czi. 

- The tabulation of the files is correct. 

- Marker names are within expectations. 

- All slides have the same round/versions. 

- All slides/rounds/versions have the same channels and the same names. 

### Arguments
```
python src/00_file_parser/czi_files_qc.py --directory <directory> --output_txt <output_txt>
```

| Argument       | Description                                                                                                           |
|----------------|-----------------------------------------------------------------------------------------------------------------------|
| `--directory`  | Path to the parent directory where the raw czi files are stored (dir). Example: `/path/to/czi_data_files_folder`      |
| `--output_txt` | Path to the output txt where the QC file will be stored (.txt). Example: `/path/to/project_directory/czi_qc_file.txt` |


### Output
The output file is a report containing the following information
```
Check1 - File format QC: PASSED.
Check2 - File tabulation QC: PASSED.
Check3 - Round naming QC: PASSED.
Check4 - Version naming QC: PASSED.
Check5 - Channel naming QC: PASSED.
Check6 - Round/Versions per slide QC: PASSED.
Check7 - Channels per Slide/Round/Version QC: PASSED.
```

If there was a problem at specific checkpoint (e.g. file is incorrectly named), the programme will stop and provide the corresponding information. Example:

```
Check1 - File format QC: PASSED.
Check2 - File tabulation QC: PASSED.
Check3 - File tabulation mismatch: /benchmarking_MILAN/R06/file_name.czi
```

## 2. Experimental design

---

 **Script:** [czi_extract_channel_metadata.py](src/00_file_parser/czi_extract_channel_metadata.py)

### Description
This function reads all the .czi files in the input directory (folder and subfolders) and generates a map from channel numbers (C0, C1, C2, etc.) to channel names (DAPI, FITC, AF, etc.). 
### Arguments
```
python src/00_file_parser/czi_extract_channel_metadata.py --directory <path_to_czis/> --output_csv_channels <path_to_output_csv/> --output_csv_slides <path_to_output_csv_slides/>
```
| Argument              | Description                                                                                                                                             |
|-----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| `directory`           | path to the parent directory where the raw czi files are stored (dir). Example: `/path/to/data_files`                                                   |
| `output_csv_channels` | path to the output CSV where the channel metadata will be stored (.csv). Example: `/path/to/project_directory/experimental_design/channel_names.csv`    |
| `output_csv_slides`   | path to the output CSV where the slides metadata will be stored (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_slides.csv` |


Output_csv_channels has the following columns:
- `channel_id` - channel name (DAPI, FITC, etc.); FITC_AF/AF_FITC is converted AF
- `channel_number` - channel number (C0, C1, C2, etc.)
- `czi_file` - full path to the czi file
- `basename` basename(czi_file)
- `slide_id` - identifier for the slide using the naming convention
- `round_number` - identifier for the round
- `version_id` - identifier for the version
- `project_id` - identifier for the project
- `user_id` - identifier for the user who acquired the data

Output_csv_slides has the following columns:
 `slide_id` - identifier for the slide
 `folder` -  name of the folder

[//]: # (### Output)

[//]: # (The generated csv file content is displayed in the software. The user needs to define, confirm or adapt channel names. )

[//]: # (Each slide appears as a different tab. Within each tab, the columns are the channels, the rows are the round/versions.  )

[//]: # ()
[//]: # (<!-- Add pic -->)

[//]: # ()
[//]: # (In the next step the user needs to provide the following information:)

[//]: # (- Reference round: round to be used as a reference for registration/segmentation. )

[//]: # (- Reference version: version of the reference round to be used for registration/segmentation)

[//]: # (- Reference  channel: channel to be used as reference for downstream steps. Typically DAPI. )

[//]: # ()
[//]: # (The user can validate information per slide or use ‘Apply All’. )

[//]: # (After this information has been extracted, we can create a dummy template for the experimental design. )

[//]: # (The number of rounds, channels and versions can be automatically filled. )

[//]: # (The user need to define the markers for the rest of the channels. Marker names need to be alphanumeric &#40;‘-’ like in HLA-DR is not allowed&#41;. )

[//]: # (This can be done directly in the GUI or by importing a csv file. )

[//]: # (Channel names and round names must match the ones in the template. )

[//]: # (The user has the option, to select whether a marker gets processed further or not.)

## 3. Data parsing

---

 **Script:** [czi_generate_csv_joblist.R](src/00_file_parser/czi_generate_csv_joblist.R)

### Description
Czi files are processed to extract individual tiles and the corresponding metadata. 
`czi_generate_csv_joblist.R` lists all the czi files in the project’s folder and generates a csv file listing all the jobs that need to be run in the next step. 
### Arguments
```
Rscript src/00_file_parser/czi_generate_csv_joblist.R --path.input.folder <path_to_input_project_folder/> --path.input.channel.dictionary <path_to_input_channel_dictionary/> --path.output.folder <path_to_output_tiles/> --path.output.csv <path_to_output_csv_joblist/>
```

| Argument                  | Description                                                                                                                                                      |
|---------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path.input.folder`            | Path to the parent directory where the raw czi files are stored (dir). Example: `/path/to/data_files`                                                            |
| `path.input.channel.dictionary`| Path to the CSV file mapping numeric (C0, C1, ...) to alphabetic (DAPI, FITC, ...) channel names (.csv). Example: `/path/to/project_directory/channel_names.csv` |
| `path.output.folder`           | Path to the output directory where the processed tiles will be saved (dir). Example: `/path/to/project_directory/output_tiles_tiffs`                             |
| `path.output.csv`              | Path to the output CSV file where the list of jobs will be stored (.csv). Example: `/path/to/project_directory/czi_extraction_csv.csv`                           |


---

 **Script:** [czi_reader.py](src/00_file_parser/czi_reader.py)


### Description
`czi_reader.py` reads an input czi given a full path and extracts all the tiles and metadata in a predefined output directory. 

### Arguments
```
Rscript src/00_file_parser/czi_generate_csv_joblist.R --imfilename <path_to_input_data/> --channel_names_dictionary <path_to_channel_dictionary/> --output_folder <path_to_output_tiles/> 
```
| Argument        | Description                                                                                                                                                      |
|-----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `imfilename`    | Path to the CZI file for the project/experiment (.czi). Example: `/path/to/data_files/subfolder/czi_file.czi`                                                    |
| `channel_names_dictionary`             | Path to the CSV file mapping numeric (C0, C1, ...) to alphabetic (DAPI, FITC, ...) channel names (.csv). Example: `/path/to/project_directory/channel_names.csv` |
| `output_folder` | Path to the output directory where the raw tiles will be saved (.tiff). Example: `/path/to/project_directory/output_tiles_tiffs`                                 |


---

**Script:** [run_czi_extraction.py](src/00_file_parser/run_czi_extraction.py)

### Description
It orchestrates the data parsing. It requires the output CSV file of [czi_generate_csv_joblist.R](src/00_file_parser/czi_generate_csv_joblist.R) and [czi_reader.py](src/00_file_parser/czi_reader.py) script  as positional arguments

### Arguments
```
python run_czi_extraction.py <path_to_output_csv_joblist/> czi_reader.py
```
| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `path_to_output_csv_joblist`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/czi_extraction_csv.csv` |




