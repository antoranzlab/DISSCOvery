<h1 align="center"> Technologies overview </h1>

## Table of content
DISSCOvery is prepared to analyze the data coming from MILAN, LunaPhore (COMET) or Akoya (PhenoCycler). Its pipeline prepares the data coming from each of the platform in similar, though not identicial way. 
Especially the first steps differs between the technologies, depending on the platform of choice.  

Some steps are not self-contained and use the scripts related to other steps, or required re-running some modules. 

[1. MILAN](#milan)

[2. LunaPhore (COMET)]()

[3. Akoya (PhenoCycler)]()

---

# MILAN

---

#### Work tree
1. [File parsing](src/01_file_parser) 
2. [Flat Field Correction(FFC)](src/02_FFC) 
3. [Hard stitching](src/03_hard_stitching)
4. [Smart Tissue Selection (STS)](src/04_STS) 
5. [Artifact detection](src/05_artifacts_detection)
6. [Split scenes](src/06_split_scenes)
7. [Stitching and registration](src/07_stitching_registration)
8. [Autofluorescence subtraction](src/08_AFS)
9. [Cell segmentation](src/09_segmentation)
10. [Feature extraction](src/10_feature_extraction)
11. [Cell identification](src/11_cell_identification)



---

# LunaPhore (COMET)

---

#### Work tree
In the contrary to other technologies, the data coming from LunaPhore are already partially preprocessed. 
Therefore, some of the data preparation steps are not necessary.


1. [Quality control and file parsing](src/01_file_parser)
2. [Resize images](src/03_hard_stitching)
3. [Smart Tissue Selection (STS)](src/04_STS) 
4. [Artifact detection](src/05_artifacts_detection)
5. [Split scenes](src/06_split_scenes)
6. [Autofluorescence subtraction](src/08_AFS)
7. [Cell segmentation](src/09_segmentation)
8. [Feature extraction](src/10_feature_extraction)
9. [Cell identification](src/11_cell_identification)





---

# Akoya (PhenoCycler)

---

#### Work tree

1. [Quality control and file parsing](src/01_file_parser) 
2. [Flat Field Correction(FFC)](src/02_FFC) 
3. [Rebuild a db resize images after FFC](src/03_hard_stitching)
4. [Smart Tissue Selection (STS)](src/04_STS) 
5. [Artifact detection](src/05_artifacts_detection)
6. [Split scenes](src/06_split_scenes)
7. [Autofluorescence subtraction](src/08_AFS)
8. [Cell segmentation](src/09_segmentation)
9. [Feature extraction](src/10_feature_extraction)
10. [Cell identification](src/11_cell_identification)

