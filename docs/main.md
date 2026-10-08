# DISSCOvery

<p align="center">
<img src="https://github.com/antoranzlab/DISSCOvery/blob/main/docs/images/main.png" width="100">
</p>

DISSCOvery is prepared to analyze the data coming from MILAN, LunaPhore (COMET) or Akoya (PhenoCycler). Its pipeline prepares the data coming from each of the platform in similar, though not identicial way.
Especially the first steps differs between the technologies, depending on the platform of choice.
Some steps are not self-contained and use the scripts related to other steps, or required re-running some modules.

## MILAN

Image analysis for MILAN is the most complex one, since it requires both Flat Field Correction and Registration of the images. 
The graph below summarizes all pipeline processes required by MILAN. 
"Quality Control" label marks the points where teh data output should be control and corrected if needed by the user before moving to the next step. 

<div align="center">

```mermaid
flowchart 
    classDef coloring fill:#6d9a8a, stroke:#468e74, color:#ffffff
    classDef coloring2 fill:#ffffff, stroke:#6d9a8a

    DP[1. Data parsing] --> FFC[2. Flat Field Correction]
    FFC[2. Flat Field Correction] --> HS[3. Hard stitching]
    HS[3. Hard stitching] -- Quality Control --> STS[4. Smart Tissue Selection]
    STS[4. Smart Tissue Selection] -- Quality Control --> Q[5. QUALIFAI: Artifact detection]
    Q[5. QUALIFAI: Artifact detection] -- Quality Control --> SS[6. Split scenes]
    SS[6. Split scenes] --> SR[7. Stitching and registration]
    SR[7. Stitching and registration] -- Quality Control --> AFS[8. Autofluorescence subtraction]
    AFS[8. Autofluorescence subtraction] -- Quality Control --> CS[9. Cell segmentation]
    CS[9. Cell segmentation] -- Quality Control --> FE[10. Feature extraction]
    FE[10. Feature extraction] --> CI[11. Cell identification]

    class DP coloring
    class FFC coloring
    class HS coloring
    class STS coloring
    class Q coloring
    class SS coloring
    class SR coloring
    class AFS coloring
    class CS coloring
    class FE coloring
    class CI coloring
    
```

</div>

More information about each module for MILAN can be found here:

[1. Data parsing](https://antoranzlab.github.io/DISSCOvery/01_MILAN_parser/)

[2. Flat Field Correction](https://antoranzlab.github.io/DISSCOvery/02_FFC/)

[3. Hard stitching](https://antoranzlab.github.io/DISSCOvery/03_hard_stitching_MILAN/)

[4. Smart Tissue Selection](https://antoranzlab.github.io/DISSCOvery/04_sts_MILAN/)

[5. QUALIFAI: Artifact detection](https://antoranzlab.github.io/DISSCOvery/05_QUALIFAI/)

[6. Split scenes](https://antoranzlab.github.io/DISSCOvery/06_split_scenes_MILAN/)

[7. Stitching and registration](https://antoranzlab.github.io/DISSCOvery/07_registration/)

[8. Autofluorescence subtraction](https://antoranzlab.github.io/DISSCOvery/08_AFS/)

[9. Cell segmentation](https://antoranzlab.github.io/DISSCOvery/09_segmentation/)

[10. Feature extraction](https://antoranzlab.github.io/DISSCOvery/10_feature_extraction/)

[11. Cell identification Part 1](https://antoranzlab.github.io/DISSCOvery/11_cell_identification1/) & [11. Cell identification Part 2](https://antoranzlab.github.io/DISSCOvery/11_cell_identification2/)



## COMET

Comet image preprocesssing is the simplest one out of all three available technologies, since the scanner conduct registration and flat field correction already. 
The graph below summarizes all pipeline processes required by COMET. 
"Quality Control" label marks the points where teh data output should be control and corrected if need by the user before moving to the next step. 

```mermaid
flowchart 
    classDef coloring fill:#6d9a8a, stroke:#468e74, color:#ffffff
    classDef coloring2 fill:#ffffff, stroke:#6d9a8a

    DP[1. Data parsing] --> HS[2. Resize images]
    HS[2. Resize images] --> STS[3. Smart Tissue Selection]
    STS[3. Smart Tissue Selection] -- Quality Control --> Q[4. QUALIFAI: Artifact detection]
    Q[4. QUALIFAI: Artifact detection] -- Quality Control --> SS[5. Split scenes]
    SS[5. Split scenes] --> AFS[6. Autofluorescence subtraction]
    AFS[6. Autofluorescence subtraction] -- Quality Control --> CS[7. Cell segmentation]
    CS[7. Cell segmentation] -- Quality Control --> FE[8. Feature extraction]
    FE[8. Feature extraction] --> CI[9. Cell identification]

    class DP coloring
    class FFC coloring
    class HS coloring
    class STS coloring
    class Q coloring
    class SS coloring
    class SR coloring
    class AFS coloring
    class CS coloring
    class FE coloring
    class CI coloring
    
```

More information about each module for COMET can be found here:


[1. Data parsing](https://antoranzlab.github.io/DISSCOvery/01_COMET_parser/)

[2. Resize images](https://antoranzlab.github.io/DISSCOvery/03_hard_stitching_COMET/)

[3. Smart Tissue Selection](https://antoranzlab.github.io/DISSCOvery/04_sts_COMET/)

[4. QUALIFAI: Artifact detection](https://antoranzlab.github.io/DISSCOvery/05_QUALIFAI/)

[5. Split scenes](https://antoranzlab.github.io/DISSCOvery/06_split_scenes_COMET_AKOYA/)

[6. Autofluorescence subtraction](https://antoranzlab.github.io/DISSCOvery/08_AFS/)

[7. Cell segmentation](https://antoranzlab.github.io/DISSCOvery/09_segmentation/)

[8. Feature extraction](https://antoranzlab.github.io/DISSCOvery/10_feature_extraction/)

[9. Cell identification Part 1](https://antoranzlab.github.io/DISSCOvery/11_cell_identification1/) & [11. Cell identification Part 2](https://antoranzlab.github.io/DISSCOvery/11_cell_identification2/)


## AKOYA

Images from AKOYA are already stitched, however the flat field correction is still required. 
Therefore, teh complexity of image preprocessing for AKOAY falls between COMET and MILAN

<div align="center">

```mermaid
flowchart 
    classDef coloring fill:#6d9a8a, stroke:#468e74, color:#ffffff
    classDef coloring2 fill:#ffffff, stroke:#6d9a8a

    DP[1. Data parsing] --> FFC[2. Flat Field Correction]
    FFC[2. Flat Field Correction] --> HS[3. Rebuild and Resize]
    HS[3. Rebuild and Resize] -- Quality Control --> STS[4. Smart Tissue Selection]
    STS[4. Smart Tissue Selection] -- Quality Control --> Q[5. QUALIFAI: Artifact detection]
    Q[5. QUALIFAI: Artifact detection] -- Quality Control --> SS[6. Split scenes]
    SS[6. Split scenes] --> AFS[7. Autofluorescence subtraction]
    AFS[7. Autofluorescence subtraction] -- Quality Control --> CS[8. Cell segmentation]
    CS[8. Cell segmentation] -- Quality Control --> FE[9. Feature extraction]
    FE[9. Feature extraction] --> CI[10. Cell identification]

    class DP coloring
    class FFC coloring
    class HS coloring
    class STS coloring
    class Q coloring
    class SS coloring
    class SR coloring
    class AFS coloring
    class CS coloring
    class FE coloring
    class CI coloring
    
```

</div>


More information about each module for AKOYA can be found here:

[1. Data parsing](https://antoranzlab.github.io/DISSCOvery/01_AKOYA_parser/)

[2. Flat Field Correction](https://antoranzlab.github.io/DISSCOvery/02_FFC/)

[3. Rebuild and Resize](https://antoranzlab.github.io/DISSCOvery/03_hard_stitching_AKOYA/)

[3. Smart Tissue Selection](https://antoranzlab.github.io/DISSCOvery/04_sts_AKOYA/)

[4. QUALIFAI: Artifact detection](https://antoranzlab.github.io/DISSCOvery/05_QUALIFAI/)

[5. Split scenes](https://antoranzlab.github.io/DISSCOvery/06_split_scenes_COMET_AKOYA/)

[6. Autofluorescence subtraction](https://antoranzlab.github.io/DISSCOvery/08_AFS/)

[7. Cell segmentation](https://antoranzlab.github.io/DISSCOvery/09_segmentation/)

[8. Feature extraction](https://antoranzlab.github.io/DISSCOvery/10_feature_extraction/)

[9. Cell identification Part 1](https://antoranzlab.github.io/DISSCOvery/11_cell_identification1/) & [11. Cell identification Part 2](https://antoranzlab.github.io/DISSCOvery/11_cell_identification2/)



