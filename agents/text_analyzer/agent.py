def run(task: str) -> str:
    char_count = len(task)
    word_count = len(task.split())
    return (
        "텍스트 분석 완료!\n"
        f"입력 내용: {task}\n"
        f"글자 수: {char_count}\n"
        f"단어 수: {word_count}"
    )
