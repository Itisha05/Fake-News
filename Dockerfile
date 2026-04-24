# Base Python Image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
# We use --no-cache-dir to keep the image size small
RUN pip install --no-cache-dir -r requirements.txt

# Download required NLTK corpora during the build phase
RUN python -m nltk.downloader stopwords vader_lexicon

# Copy the rest of the application code
COPY . .

# Expose port (Hugging Face Spaces uses 7860 by default for Docker spaces)
EXPOSE 7860

# Command to run the application using gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:7860", "--workers", "2", "--timeout", "120", "app:app"]
