import express from 'express';
import cors from 'cors';
import fs from 'fs/promises';
import path from 'path';

const app = express();
const PORT = 3001;

// Directory to search — change this to scan a different folder
const SEARCH_DIR = 'C:\\Users\\dell\\AIMIND';

const IGNORED_DIRS = new Set([
  'node_modules', '.git', '.vscode', '__pycache__',
  '.next', 'dist', 'build', '.cache', '.idea'
]);

// File type categories
const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico']);
const VIDEO_EXTS = new Set(['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.webm']);
const AUDIO_EXTS = new Set(['.mp3', '.wav', '.flac', '.ogg', '.aac', '.m4a']);
const DOC_EXTS = new Set(['.pdf', '.doc', '.docx', '.txt', '.md', '.rtf', '.odt']);
const CODE_EXTS = new Set(['.js', '.jsx', '.ts', '.tsx', '.py', '.java', '.c', '.cpp', '.html', '.css', '.json', '.xml', '.go', '.rs', '.rb', '.php', '.sh', '.bat']);
const DATA_EXTS = new Set(['.csv', '.xlsx', '.xls', '.pptx', '.ppt']);
const ARCHIVE_EXTS = new Set(['.zip', '.rar', '.7z', '.tar', '.gz']);

function getCategory(ext, isDirectory) {
  if (isDirectory) return 'folder';
  if (IMAGE_EXTS.has(ext)) return 'image';
  if (VIDEO_EXTS.has(ext)) return 'video';
  if (AUDIO_EXTS.has(ext)) return 'audio';
  if (DOC_EXTS.has(ext)) return 'document';
  if (CODE_EXTS.has(ext)) return 'code';
  if (DATA_EXTS.has(ext)) return 'data';
  if (ARCHIVE_EXTS.has(ext)) return 'archive';
  return 'other';
}

// Mock descriptions — in real app, these would come from AI
const mockDescriptions = {
  image: [
    'Photo showing a scenic landscape with vibrant colors',
    'Image of a group of people posing outdoors',
    'Close-up photograph with detailed textures',
    'Candid shot captured in natural lighting',
    'Digital artwork with abstract patterns',
  ],
  video: [
    'Video recording of an event or presentation',
    'Short clip with background music',
    'Screen recording of a tutorial walkthrough',
  ],
  audio: [
    'Audio track, possibly music or voice recording',
    'Sound file with ambient background audio',
  ],
  document: [
    'Text document containing structured content',
    'Written notes or report with multiple sections',
    'Reference material with detailed information',
  ],
  code: [
    'Source code file with function definitions and logic',
    'Configuration or script file for project setup',
    'Module with imports and exported utilities',
  ],
  data: [
    'Spreadsheet or dataset with tabular information',
    'Presentation slides with visual content',
  ],
  archive: [
    'Compressed archive containing multiple files',
  ],
  folder: [
    'Directory containing project files and subdirectories',
    'Folder with organized resources',
  ],
  other: [
    'Miscellaneous file',
  ],
};

function getMockDescription(category, filename) {
  const descriptions = mockDescriptions[category] || mockDescriptions.other;
  // Use filename hash to get a consistent but varied description
  const hash = [...filename].reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return descriptions[hash % descriptions.length];
}

app.use(cors());

async function walkDir(dir, baseDir, results = [], maxResults = 500) {
  if (results.length >= maxResults) return results;

  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return results;
  }

  for (const entry of entries) {
    if (results.length >= maxResults) break;
    if (IGNORED_DIRS.has(entry.name)) continue;

    const fullPath = path.join(dir, entry.name);
    const relativePath = path.relative(baseDir, fullPath);

    try {
      const stat = await fs.stat(fullPath);
      const ext = entry.isDirectory() ? '' : path.extname(entry.name).toLowerCase();
      const category = getCategory(ext, entry.isDirectory());
      const description = getMockDescription(category, entry.name);

      results.push({
        name: entry.name,
        path: relativePath,
        fullPath,
        size: stat.size,
        modified: stat.mtime,
        isDirectory: entry.isDirectory(),
        extension: ext,
        category,
        description,
      });

      if (entry.isDirectory()) {
        await walkDir(fullPath, baseDir, results, maxResults);
      }
    } catch {
      // Skip files we can't stat
    }
  }

  return results;
}

// Simple relevance scoring
function scoreMatch(file, queryWords) {
  let score = 0;
  const nameLower = file.name.toLowerCase();
  const descLower = file.description.toLowerCase();
  const pathLower = file.path.toLowerCase();

  for (const word of queryWords) {
    // Exact name match is strongest
    if (nameLower === word) score += 100;
    // Name contains the word
    else if (nameLower.includes(word)) score += 50;
    // Description contains the word
    if (descLower.includes(word)) score += 30;
    // Path contains the word
    if (pathLower.includes(word)) score += 10;
  }

  return score;
}

app.get('/api/files', async (req, res) => {
  const query = (req.query.q || '').toLowerCase().trim();

  try {
    const allFiles = await walkDir(SEARCH_DIR, SEARCH_DIR);

    if (!query) {
      return res.json({ topMatches: [], rest: [], total: 0 });
    }

    const queryWords = query.split(/\s+/).filter(Boolean);

    // Score every file
    const scored = allFiles.map(f => ({ ...f, score: scoreMatch(f, queryWords) }));

    // Top 5 matches (must have score > 0)
    const matched = scored
      .filter(f => f.score > 0)
      .sort((a, b) => b.score - a.score);

    const topMatches = matched.slice(0, 5);

    // All other files (everything not in top matches)
    const topPaths = new Set(topMatches.map(f => f.fullPath));
    const rest = scored.filter(f => !topPaths.has(f.fullPath));

    res.json({ topMatches, rest, total: allFiles.length });
  } catch (err) {
    res.status(500).json({ error: 'Failed to read directory', details: err.message });
  }
});

// Context endpoint: returns a file's folder siblings + related files by category
app.get('/api/files/context', async (req, res) => {
  const filePath = req.query.path || '';

  try {
    const allFiles = await walkDir(SEARCH_DIR, SEARCH_DIR);
    const file = allFiles.find(f => f.path === filePath);

    if (!file) {
      return res.status(404).json({ error: 'File not found' });
    }

    // Parent folder
    const parentDir = path.dirname(filePath);

    // Sibling files (same folder, excluding the file itself), cap at 8
    const siblings = allFiles
      .filter(f => path.dirname(f.path) === parentDir && f.path !== filePath)
      .slice(0, 8);

    // Related files (same category, different folder), cap at 6
    const related = allFiles
      .filter(f =>
        f.category === file.category &&
        f.path !== filePath &&
        path.dirname(f.path) !== parentDir
      )
      .slice(0, 6);

    res.json({
      file,
      parentDir: parentDir === '.' ? '' : parentDir,
      siblings,
      related,
    });
  } catch (err) {
    res.status(500).json({ error: 'Failed to get context', details: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`File search server running on http://localhost:${PORT}`);
  console.log(`Searching in: ${SEARCH_DIR}`);
});
