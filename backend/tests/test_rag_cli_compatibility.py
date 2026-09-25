from app.rag.ingestion.cli import build_parser


def test_prepare_foundation_defaults_to_ignored_docker_runtime_output() -> None:
    args = build_parser().parse_args(
        ["prepare-foundation", "--foundation-path", "/data/academic_foundation"]
    )

    assert args.output_dir == "/data/prepared_rag"
