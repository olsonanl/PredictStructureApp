cwlVersion: v1.2
class: CommandLineTool

label: "Chai-1 Structure Prediction"
doc: |
  Runs chai-lab fold inside the all-in-one container.
  Inputs match the native chai-lab CLI flags.

requirements:
  DockerRequirement:
    dockerPull: dxkb/predict-structure-all:latest-gpu
  InitialWorkDirRequirement:
    listing:
      - $(inputs.input_fasta)
  NetworkAccess:
    networkAccess: true
  ResourceRequirement:
    coresMin: 8
    ramMin: 65536
    ramMax: 98304

hints:
  cwltool:CUDARequirement:
    cudaVersionMin: "11.8"
    cudaDeviceCountMin: 1
    cudaDeviceCountMax: 1

baseCommand: [/opt/conda-chai/bin/chai-lab, fold]

inputs:
  input_fasta:
    type: File
    inputBinding:
      position: 1
    doc: "Input FASTA file with entity-typed headers"

  output_directory:
    type: string
    default: output
    inputBinding:
      position: 2
    doc: "Output directory"

  num_diffn_samples:
    type: int?
    inputBinding:
      prefix: --num-diffn-samples
    doc: "Number of diffusion samples"

  num_trunk_recycles:
    type: int?
    inputBinding:
      prefix: --num-trunk-recycles
    doc: "Number of trunk recycles"

  num_diffn_timesteps:
    type: int?
    inputBinding:
      prefix: --num-diffn-timesteps
    doc: "Number of diffusion timesteps"

  num_trunk_samples:
    type: int?
    inputBinding:
      prefix: --num-trunk-samples
    doc: "Number of trunk samples"

  seed:
    type: int?
    inputBinding:
      prefix: --seed
    doc: "Random seed"

  device:
    type: string?
    inputBinding:
      prefix: --device
    doc: "Device (cuda or cpu)"

  msa_directory:
    type: string?
    inputBinding:
      prefix: --msa-directory
    doc: "MSA directory (Parquet format)"

  use_msa_server:
    type: boolean?
    inputBinding:
      prefix: --use-msa-server
    doc: "Use remote MSA server"

  msa_server_url:
    type: string?
    inputBinding:
      prefix: --msa-server-url
    doc: "Custom MSA server URL"

  use_templates_server:
    type: boolean?
    inputBinding:
      prefix: --use-templates-server
    doc: "Use PDB template server"

  constraint_path:
    type: string?
    inputBinding:
      prefix: --constraint-path
    doc: "Constraint JSON file"

  template_hits_path:
    type: string?
    inputBinding:
      prefix: --template-hits-path
    doc: "Pre-computed template hits"

  recycle_msa_subsample:
    type: int?
    inputBinding:
      prefix: --recycle-msa-subsample
    doc: "MSA subsample per recycle"

outputs:
  predictions:
    type: Directory
    outputBinding:
      glob: $(inputs.output_directory)

stdout: chai.log
stderr: chai.err

$namespaces:
  cwltool: http://commonwl.org/cwltool#
