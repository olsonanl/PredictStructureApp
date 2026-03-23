cwlVersion: v1.2
class: CommandLineTool

label: "Boltz-2 Structure Prediction"
doc: |
  Runs boltz predict inside the all-in-one container.
  Inputs match the native boltz CLI flags.

requirements:
  DockerRequirement:
    dockerPull: dxkb/predict-structure-all:latest-gpu
  InitialWorkDirRequirement:
    listing:
      - $(inputs.input_file)
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

baseCommand: [/opt/conda-boltz/bin/boltz, predict]

inputs:
  input_file:
    type: File
    inputBinding:
      position: 1
    doc: "Input YAML or FASTA file"

  output_dir:
    type: string
    default: output
    inputBinding:
      prefix: --out_dir
    doc: "Output directory"

  diffusion_samples:
    type: int?
    inputBinding:
      prefix: --diffusion_samples
    doc: "Number of diffusion samples"

  recycling_steps:
    type: int?
    inputBinding:
      prefix: --recycling_steps
    doc: "Number of recycling steps"

  sampling_steps:
    type: int?
    inputBinding:
      prefix: --sampling_steps
    doc: "Number of sampling steps"

  output_format:
    type: string?
    inputBinding:
      prefix: --output_format
    doc: "Output format (mmcif or pdb)"

  accelerator:
    type: string?
    inputBinding:
      prefix: --accelerator
    doc: "Accelerator (gpu or cpu)"

  use_msa_server:
    type: boolean?
    inputBinding:
      prefix: --use_msa_server
    doc: "Use remote MSA server"

  msa_server_url:
    type: string?
    inputBinding:
      prefix: --msa_server_url
    doc: "Custom MSA server URL"

  use_potentials:
    type: boolean?
    inputBinding:
      prefix: --use_potentials
    doc: "Enable potential terms"

  write_full_pae:
    type: boolean?
    inputBinding:
      prefix: --write_full_pae
    doc: "Write full PAE matrix"

outputs:
  predictions:
    type: Directory
    outputBinding:
      glob: $(inputs.output_dir)

stdout: boltz.log
stderr: boltz.err

$namespaces:
  cwltool: http://commonwl.org/cwltool#
