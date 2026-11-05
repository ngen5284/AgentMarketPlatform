
def run(task: str) -> str:
    """전달받은 작업을 처리합니다."""
    return (
        "로컬 에이전트 실행 성공!\n"
        f"에이전트: 테스트 에이전트\n"
        f"요청 내용: {task}"
    )

