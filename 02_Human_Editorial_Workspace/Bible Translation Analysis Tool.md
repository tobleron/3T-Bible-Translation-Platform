# Bible Translation Analysis Tool

A specialized tool for analyzing Bible translations through a 4-prompt analysis chain to generate JSON files for translation justification documentation.

## Overview

This tool repurposes the existing AI chat infrastructure to create a dedicated Bible translation analysis workflow. It processes Bible passages verse-by-verse through multiple analytical prompts and generates comprehensive JSON output files.

## Features

- **4-Prompt Analysis Chain**: Each verse is analyzed through:
  
  1. Translation Analysis
  2. Stylistic Score
  3. Theological Fidelity
  4. Passage-Level Synthesis & Analysis

- **Flexible Bible File Support**: Works with JSON files containing original texts (Greek/Hebrew) and translations

- **Automated Processing**: Processes entire passages automatically, handling each verse individually before performing passage-level analysis

- **Rich Output**: Generates detailed JSON files with all analyses, timestamps, and metadata

- **User-Friendly Interface**: Interactive prompts guide you through the entire process

## Installation

### Prerequisites

- Python 3.11+
- Required Python packages (install with pip):

```bash
pip install rich pyyaml openai requests
```

### Setup

1. **Configure API Access**: Update `config.yaml` with your OpenAI API key or ensure `OPENAI_API_KEY` environment variable is set.

2. **Prepare Bible Files**: Place your Bible JSON files in the `flat_bibles/` directory. The tool supports various JSON structures:
   
   - `data[book][chapter][verse]`
   - `data["Book Chapter:Verse"]`
   - Nested structure with books/chapters/verses arrays

3. **Ensure Prompt Files**: The following prompt files should be in the same directory:
   
   - `01_translation_analysis.txt`
   - `02_stylistic_score.txt`
   - `03_theological_fidelity.txt`
   - `04_Passage-LevelSynthesis&Analysis.txt`

## Usage

### Running the Tool

```bash
python3 bible_translation_tool.py
```

### Workflow

1. **Select LLM Service**: Choose between Ollama (local) or OpenAI (cloud)
2. **Select Model**: Pick from available models for your chosen service
3. **Enter Passage**: Specify the passage to analyze (e.g., "John 1:1-5")
4. **Select Files**: Choose original text and translation JSON files
5. **Processing**: The tool automatically:
   - Extracts verses from both files
   - Processes each verse through prompts 1-3
   - Runs passage-level analysis (prompt 4)
   - Saves final JSON output

### Example Session

```
Enter Passage Reference: John 1:1-3
Select Original Text File: sample_original.json
Select Translation File: sample_translation.json
✅ Extracted 3 verses
Processing 3 verses... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%
✅ Analysis complete! Output saved to: output/John_001_001_003.json
```

## File Structure

```
bible_translation_tool/
├── bible_translation_tool.py      # Main application
├── llm_clients.py                  # LLM client implementations
├── session_manager.py              # Session management (reused)
├── config.yaml                     # Configuration file
├── flat_bibles/                    # Bible JSON files directory
│   ├── sample_original.json        # Example original text
│   └── sample_translation.json     # Example translation
├── output/                         # Generated analysis files
├── 01_translation_analysis.txt     # Prompt 1
├── 02_stylistic_score.txt         # Prompt 2
├── 03_theological_fidelity.txt    # Prompt 3
└── 04_Passage-LevelSynthesis&Analysis.txt  # Prompt 4
```

## Output Format

The tool generates JSON files with the following structure:

```json
{
  "passage_reference": "John 1:1-3",
  "verse_results": [
    {
      "reference": "John 1:1",
      "original": "Greek/Hebrew text",
      "translation": "English translation",
      "analyses": {
        "translation_analysis": {
          "prompt_type": "translation_analysis",
          "response": "Analysis response",
          "timestamp": "2025-07-13T05:03:39.062995"
        },
        "stylistic_score": { ... },
        "theological_fidelity": { ... }
      }
    }
  ],
  "passage_analysis": {
    "prompt_type": "passage_synthesis",
    "response": "Passage-level analysis",
    "timestamp": "..."
  },
  "metadata": {
    "model": "gpt-4.1-mini",
    "temperature": 0.7,
    "total_verses": 3
  }
}
```

## Bible JSON File Formats

The tool supports multiple JSON structures for Bible files:

### Format 1: Nested by Book/Chapter/Verse

```json
{
  "John": {
    "1": {
      "1": "Verse text here",
      "2": "Verse text here"
    }
  }
}
```

### Format 2: Flat with Reference Keys

```json
{
  "John 1:1": "Verse text here",
  "John 1:2": "Verse text here"
}
```

### Format 3: Structured Arrays

```json
{
  "books": [
    {
      "name": "John",
      "chapters": [
        {
          "number": 1,
          "verses": [
            {"number": 1, "text": "Verse text here"}
          ]
        }
      ]
    }
  ]
}
```

## Customization

### Adding New Prompts

1. Create a new prompt text file
2. Update the `_load_prompts()` method in `bible_translation_tool.py`
3. Modify the processing logic to include your new prompt

### Modifying JSON Structure Support

Update the `_find_verse_in_data()` method to support additional JSON structures.

### Changing Output Format

Modify the `_save_final_json()` method to customize the output structure.

## Troubleshooting

### Common Issues

1. **Module Not Found**: Install required packages with pip
2. **API Key Errors**: Ensure your OpenAI API key is correctly configured
3. **File Not Found**: Check that Bible JSON files are in the `flat_bibles/` directory
4. **Model Errors**: Verify model names in `config.yaml` match available models

### Error Handling

The tool includes comprehensive error handling for:

- Missing files
- Invalid passage formats
- API failures
- JSON parsing errors

## Integration with Existing Workflow

This tool integrates seamlessly with your existing Bible translation project:

1. **Input**: Use your existing Bible JSON files
2. **Processing**: Leverages your 4-prompt analysis system
3. **Output**: Generates structured JSON for your justification book
4. **Future Processing**: JSON files can be processed by additional tools to generate the final justification book

## Performance Considerations

- Processing time depends on passage length and LLM response time
- Progress bars show real-time processing status
- Each verse requires 3 API calls (prompts 1-3) plus 1 passage-level call (prompt 4)
- Consider using faster models for large passages

## Future Enhancements

Potential improvements for future versions:

1. **Batch Processing**: Process multiple passages in sequence
2. **Resume Capability**: Resume interrupted analyses
3. **Custom Prompt Templates**: User-defined prompt templates
4. **Export Formats**: Additional output formats (PDF, Word, etc.)
5. **Parallel Processing**: Process multiple verses simultaneously
6. **Caching**: Cache results to avoid re-processing

## Support

For issues or questions:

1. Check the troubleshooting section
2. Verify your configuration files
3. Test with the provided sample files
4. Review the generated JSON output for errors
