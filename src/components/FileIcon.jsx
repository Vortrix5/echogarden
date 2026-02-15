const iconMap = {
  folder: '📁',
  image: '🖼️',
  video: '🎬',
  audio: '🎵',
  pdf: '📄',
  code: '💻',
  text: '📝',
  archive: '📦',
  data: '📊',
  exe: '⚙️',
  default: '📎',
};

const extensionCategories = {
  '.jpg': 'image', '.jpeg': 'image', '.png': 'image', '.gif': 'image',
  '.bmp': 'image', '.svg': 'image', '.webp': 'image', '.ico': 'image',
  '.mp4': 'video', '.avi': 'video', '.mkv': 'video', '.mov': 'video', '.wmv': 'video',
  '.mp3': 'audio', '.wav': 'audio', '.flac': 'audio', '.ogg': 'audio', '.aac': 'audio',
  '.pdf': 'pdf',
  '.js': 'code', '.jsx': 'code', '.ts': 'code', '.tsx': 'code',
  '.py': 'code', '.java': 'code', '.c': 'code', '.cpp': 'code',
  '.html': 'code', '.css': 'code', '.json': 'code', '.xml': 'code',
  '.go': 'code', '.rs': 'code', '.rb': 'code', '.php': 'code',
  '.sh': 'code', '.bat': 'code', '.ps1': 'code',
  '.txt': 'text', '.md': 'text', '.log': 'text', '.csv': 'text',
  '.zip': 'archive', '.rar': 'archive', '.7z': 'archive', '.tar': 'archive', '.gz': 'archive',
  '.xlsx': 'data', '.xls': 'data', '.doc': 'data', '.docx': 'data', '.pptx': 'data',
  '.exe': 'exe', '.msi': 'exe', '.dll': 'exe',
};

export default function FileIcon({ extension, isDirectory }) {
  if (isDirectory) return <span className="file-icon">{iconMap.folder}</span>;

  const category = extensionCategories[extension] || 'default';
  return <span className="file-icon">{iconMap[category]}</span>;
}
