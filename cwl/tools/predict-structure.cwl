cwlVersion: v1.2
class: CommandLineTool

label: "Unified Protein Structure Prediction"
doc: |
  Dispatches to Boltz-2, Chai-1, AlphaFold 2, or ESMFold via the
  predict-structure CLI.  Runs inside per-tool Docker containers.

  Tool selection is a CWL enum input that maps to a CLI subcommand.
  The correct Docker image is resolved automatically based on the
  chosen tool, maintaining the delegation pattern (one container per
  prediction tool).

  Tool-specific inputs use valueFrom expressions so they are only
  emitted on the command line when the selected tool accepts them.

  Defaults
  --------
  num_samples:          1
  num_recycles:         3
  output_format:        pdb
  device:               gpu
  sampling_steps:       200      (Boltz, Chai)
  af2_model_preset:     monomer  (AlphaFold)
  af2_db_preset:        reduced_dbs (AlphaFold)
  af2_max_template_date: 2022-01-01 (AlphaFold)

requirements:
  InlineJavascriptRequirement: {}
  DockerRequirement:
    dockerPull: |
      ${
        var images = {
          "boltz":     "dxkb/boltz-bvbrc:latest-gpu",
          "chai":      "dxkb/chai-bvbrc:latest-gpu",
          "alphafold": "wilke/alphafold",
          "esmfold":   "dxkb/esmfold-bvbrc:latest-gpu"
        };
        return images[inputs.tool];
      }
  ResourceRequirement:
    coresMin: 8
    ramMin: |
      ${
        var mem = {
          "boltz":     65536,
          "chai":      65536,
          "alphafold": 65536,
          "esmfold":   32768
        };
        return mem[inputs.tool];
      }
    ramMax: 98304
  InitialWorkDirRequirement:
    listing:
      - $(inputs.input_file)
  NetworkAccess:
    networkAccess: true

hints:
  cwltool:CUDARequirement:
    cudaVersionMin: "11.8"
    cudaDeviceCountMin: 1
    cudaDeviceCountMax: 1

baseCommand: [predict-structure]

arguments:
  - valueFrom: "--backend"
    position: 98
  - valueFrom: "subprocess"
    position: 99

# ===================================================================
#  Inputs
# ===================================================================

inputs:

  # --- Tool selection (becomes CLI subcommand) ----------------------

  tool:
    type:
      type: enum
      symbols: [boltz, chai, alphafold, esmfold]
    inputBinding:
      position: 1
    doc: "Prediction tool to use (maps to CLI subcommand)"

  input_file:
    type: File
    inputBinding:
      position: 2
    doc: "Input FASTA file (or Boltz YAML) containing protein sequences"

  # --- Global options -----------------------------------------------

  output_dir:
    type: string?
    default: "output"
    inputBinding:
      prefix: --output-dir
      position: 3
    doc: "Output directory for prediction results [default: output]"

  num_samples:
    type: int?
    default: 1
    inputBinding:
      prefix: --num-samples
    doc: "Number of structure samples to generate (Boltz, Chai) [default: 1]"

  num_recycles:
    type: int?
    default: 3
    inputBinding:
      prefix: --num-recycles
    doc: "Number of recycling iterations [default: 3]"

  seed:
    type: int?
    inputBinding:
      prefix: --seed
    doc: "Random seed for reproducibility [default: none]"

  msa:
    type: File?
    inputBinding:
      prefix: --msa
    doc: "Pre-computed MSA file (.a3m, .sto, .pqt)"

  output_format:
    type:
      - "null"
      - type: enum
        symbols: [pdb, mmcif]
    default: pdb
    inputBinding:
      prefix: --output-format
    doc: "Output structure format [default: pdb]"

  # --- Execution options --------------------------------------------

  device:
    type:
      - "null"
      - type: enum
        symbols: [gpu, cpu]
    default: gpu
    inputBinding:
      prefix: --device
    doc: "Compute device [default: gpu]"

  # --- Boltz-2 / Chai-1 options ------------------------------------

  sampling_steps:
    type: int?
    default: 200
    inputBinding:
      prefix: --sampling-steps
      valueFrom: |
        ${
          if (inputs.tool === "boltz" || inputs.tool === "chai") {
            return self;
          }
          return null;
        }
    doc: "Diffusion sampling steps (Boltz, Chai) [default: 200]"

  use_msa_server:
    type: boolean?
    default: false
    inputBinding:
      prefix: --use-msa-server
      valueFrom: |
        ${
          if (inputs.tool === "boltz" || inputs.tool === "chai") {
            return self;
          }
          return null;
        }
    doc: "Use remote MSA server for alignment generation (Boltz, Chai) [default: false]"

  msa_server_url:
    type: string?
    inputBinding:
      prefix: --msa-server-url
      valueFrom: |
        ${
          if (inputs.tool === "boltz" || inputs.tool === "chai") {
            return self;
          }
          return null;
        }
    doc: "Custom MSA server URL; implies use_msa_server (Boltz, Chai)"

  # --- Boltz-2 only ------------------------------------------------

  use_potentials:
    type: boolean?
    default: false
    inputBinding:
      prefix: --use-potentials
      valueFrom: |
        ${
          if (inputs.tool === "boltz") {
            return self;
          }
          return null;
        }
    doc: "Enable inference-time potentials (Boltz only) [default: false]"

  # --- AlphaFold 2 options -----------------------------------------

  af2_data_dir:
    type: Directory?
    inputBinding:
      prefix: --af2-data-dir
      valueFrom: |
        ${
          if (inputs.tool === "alphafold") {
            return self;
          }
          return null;
        }
    doc: "AlphaFold2 database directory (~2TB) [default: /databases]"

  af2_model_preset:
    type: string?
    default: "monomer"
    inputBinding:
      prefix: --af2-model-preset
      valueFrom: |
        ${
          if (inputs.tool === "alphafold") {
            return self;
          }
          return null;
        }
    doc: "AlphaFold2 model preset (monomer, monomer_casp14, multimer) [default: monomer]"

  af2_db_preset:
    type: string?
    default: "reduced_dbs"
    inputBinding:
      prefix: --af2-db-preset
      valueFrom: |
        ${
          if (inputs.tool === "alphafold") {
            return self;
          }
          return null;
        }
    doc: "AlphaFold2 database preset (full_dbs, reduced_dbs) [default: reduced_dbs]"

  af2_max_template_date:
    type: string?
    default: "2022-01-01"
    inputBinding:
      prefix: --af2-max-template-date
      valueFrom: |
        ${
          if (inputs.tool === "alphafold") {
            return self;
          }
          return null;
        }
    doc: "Maximum template date for AlphaFold2 (YYYY-MM-DD) [default: 2022-01-01]"

  # --- ESMFold options ----------------------------------------------

  fp16:
    type: boolean?
    default: false
    inputBinding:
      prefix: --fp16
      valueFrom: |
        ${
          if (inputs.tool === "esmfold") {
            return self;
          }
          return null;
        }
    doc: "Use half-precision (FP16) inference (ESMFold only) [default: false]"

  chunk_size:
    type: int?
    inputBinding:
      prefix: --chunk-size
      valueFrom: |
        ${
          if (inputs.tool === "esmfold") {
            return self;
          }
          return null;
        }
    doc: "Chunk size for long sequences (ESMFold only)"

  max_tokens_per_batch:
    type: int?
    inputBinding:
      prefix: --max-tokens-per-batch
      valueFrom: |
        ${
          if (inputs.tool === "esmfold") {
            return self;
          }
          return null;
        }
    doc: "Maximum tokens per batch (ESMFold only)"

# ===================================================================
#  Outputs
# ===================================================================

outputs:
  predictions:
    type: Directory
    outputBinding:
      glob: $(inputs.output_dir)
    doc: "Directory containing all prediction outputs"

  structure_files:
    type: File[]?
    outputBinding:
      glob: |
        ${
          if (inputs.output_format === "mmcif") {
            return inputs.output_dir + "/**/*.cif";
          }
          return inputs.output_dir + "/**/*.pdb";
        }
    doc: "Predicted structure files (PDB or mmCIF)"

  metadata:
    type: File?
    outputBinding:
      glob: "$(inputs.output_dir)/metadata.json"
    doc: "Prediction metadata (tool, parameters, runtime, version)"

  confidence:
    type: File?
    outputBinding:
      glob: "$(inputs.output_dir)/confidence.json"
    doc: "Confidence scores (pLDDT, pTM, per-residue)"

stdout: predict-structure.log
stderr: predict-structure.err

s:author:
  - class: s:Person
    s:name: BV-BRC Team
    s:email: help@bv-brc.org

s:license: https://spdx.org/licenses/MIT

$namespaces:
  cwltool: http://commonwl.org/cwltool#
  s: https://schema.org/

$schemas:
  - https://schema.org/version/latest/schemaorg-current-https.rdf
