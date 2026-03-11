"""Shared test fixtures."""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture
def sample_fasta(tmp_path):
    """Create a simple single-sequence FASTA file."""
    fasta = tmp_path / "test.fasta"
    fasta.write_text(">1CRN|Crambin|46 residues\nTTCCPSIVARSNFNVCRLPGTPEALCATYTGCIIIPGATCPGDYAN\n")
    return fasta


@pytest.fixture
def multi_chain_fasta(tmp_path):
    """Create a multi-chain FASTA file."""
    fasta = tmp_path / "multi.fasta"
    fasta.write_text(
        ">chainA\nMKTIIALSYIFCLVFA\n"
        ">chainB\nGIVLAAVLLLLVAGSS\n"
    )
    return fasta


@pytest.fixture
def sample_a3m(tmp_path):
    """Create a simple A3M alignment file."""
    a3m = tmp_path / "test.a3m"
    a3m.write_text(
        ">query\nTTCCPSIVARSNFNVCRLPGTPEALCATYTGCIIIPGATCPGDYAN\n"
        ">hit1\nTTCCPSIVARSNFNVCRLPGTPEALCATYTGCIIIPGATCPGDYAN\n"
        ">hit2\nTTCCASIVARSNFNVCRLPGTPEALCATYTGCIIIPGATCPGDYAN\n"
    )
    return a3m


@pytest.fixture
def tmp_output(tmp_path):
    """Create and return a temporary output directory."""
    out = tmp_path / "output"
    out.mkdir()
    return out
