
from nlp import remove_emojis, sentence_tokenizer

def test_remove_emojis():
    assert remove_emojis("Hello, world! 👋🌍") == "Hello, world!"
    assert remove_emojis("No emojis here.") == "No emojis here."
    assert remove_emojis("😀😃😄😁😆😅😂🤣😊😇") == ""

def test_sentence_tokenizer():
    parts = iter(["Hello wor", "ld. How are", " you? I am fine"])
    sentences = list(sentence_tokenizer(parts))
    assert sentences == ["Hello world.", "How are you?", "I am fine"]

if __name__ == "__main__":
    test_remove_emojis()
    test_sentence_tokenizer()
    print("All tests passed!")