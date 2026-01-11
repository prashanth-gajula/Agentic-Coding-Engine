from IPython.display import Image, display
from workflow_State.workflow_main import create_workflow

app = create_workflow()

# Generate PNG bytes
png_bytes = app.get_graph().draw_mermaid_png()

# Display in notebook
display(Image(png_bytes))

# Save to a file
output_file = "workflow_diagram.png"
with open(output_file, "wb") as f:
    f.write(png_bytes)

print(f"Diagram saved to: {output_file}")
