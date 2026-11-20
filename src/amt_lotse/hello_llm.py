from pathlib import Path
import ollama
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # which index gets you to amt-lotse/?
LETTER_PATH = PROJECT_ROOT / "data" / "samples" / "example.txt"
def read_letter() -> str:
    """
    Returns the the letter file.
    """
    return LETTER_PATH.read_text(encoding="UTF-8")



def ollama_reasponse(letter:str)->str:
    response=ollama.chat(model="qwen2.5:7b", messages= [
       {"role": "system", "content": "You explain German official letters to international students in simple English. Be accurate and never invent information."},
       {"role": "user", "content": f"Here is a letter:\n\n{letter}\n\nWhat is the deadline, the amount, and what do I have to do?"},
    ])
    return response["message"]["content"]
    
if __name__ == "__main__":
    letter = read_letter()
    answer = ollama_reasponse(letter)
    print(answer)