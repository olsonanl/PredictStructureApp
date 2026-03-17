cwlVersion: v1.2
class: CommandLineTool

label: "Unified Protein Structure Prediction"
doc: |
  Dispatches to Boltz-2, Chai-1, AlphaFold 2, or ESMFold via the
  predict-structure CLI. Runs inside per-tool Docker containers.

  Tool selection is a CWL enum input. The correct Docker image is
  resolved automatically based on the chosen tool, maintaining the
  delegation pattern (one container per prediction tool).

requirements:
  InlineJavascriptRequirement: {}
  DockerRequirement:
    dockerPull: |
      ${
        var images = {
          "boltz": "dxkb/boltz-bvbrc:latest-gpu",
          "chai": "dxkb/chai-bvbrc:latest-gpu",
          "alphafold": "wilke/alphafold",
          "esmfold": "dxkb/esmfold-bvbrc:latest-gpu"
        };
        return images[inputs.tool];
      }
  ResourceRequirement:
    coresMin: 8
    ramMin: 32768    # 32GB minimum
    ramMax: 98304    # 96GB maximum
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

inputs:
  tool:
    type:
      type: enum
      symbols: [boltz, chai, alphafold, esmfold]
    inputBinding:
      position: 1
    doc: "Prediction tool to use"

  input_file:
    type: File
    inputBinding:
      position: 2
    doc: "Input FASTA file containing protein sequences"

  output_dir:
    type: string?
    default: "output"
    inputBinding:
      prefix: --output-dir
      position: 3
    doc: "Output directory for prediction results"

  num_samples:
    type: int?
    inputBinding:
      prefix: --num-samples
    doc: "Number of structure samples (Boltz/Chai)"

  num_recycles:
    type: int?
    inputBinding:
      prefix: --num-recycles
    doc: "Number of recycling iterations"

  seed:
    type: int?
    inputBinding:
      prefix: --seed
    doc: "Random seed for reproducibility"

  device:
    type:
      - "null"
      - type: enum
        symbols: [gpu, cpu]
    inputBinding:
      prefix: --device
    doc: "Compute device (gpu or cpu)"

  msa:
    type: File?
    inputBinding:
      prefix: --msa
    doc: "MSA file (.a3m, .sto, .pqt)"

  output_format:
    type:
      - "null"
      - type: enum
        symbols: [pdb, mmcif]
    inputBinding:
      prefix: --output-format
    doc: "Output structure format"

  sampling_steps:
    type: int?
    inputBinding:
      prefix: --sampling-steps
    doc: "Sampling steps (Boltz/Chai)"

  use_msa_server:
    type: boolean?
    inputBinding:
      prefix: --use-msa-server
    doc: "Use MSA server for alignment generation"

  af2_data_dir:
    type: Directory?
    inputBinding:
      prefix: --af2-data-dir
    doc: "AlphaFold2 database directory"

  af2_model_preset:
    type: string?
    inputBinding:
      prefix: --af2-model-preset
    doc: "AlphaFold2 model preset (monomer, multimer)"

  af2_db_preset:
    type: string?
    inputBinding:
      prefix: --af2-db-preset
    doc: "AlphaFold2 database preset (full_dbs, reduced_dbs)"

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
    doc: "Predicted structure files"

  metadata:
    type: File?
    outputBinding:
      glob: "$(inputs.output_dir)/metadata.json"
    doc: "Prediction metadata (tool, params, runtime, version)"

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
