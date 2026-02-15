import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import * as THREE from 'three';

const colorByCategory = {
  image: '#F72585',
  video: '#c084fc',
  audio: '#f97316',
  document: '#8B5CF6',
  code: '#06D6A0',
  data: '#FF6B6B',
  archive: '#B5179E',
  folder: '#4CC9F0',
  other: '#94A3B8',
  search: '#FDD000',
};

function formatSize(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}

export default function GraphView({ file, onBack }) {
  const fgRef = useRef();
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [selected, setSelected] = useState(null);
  const [expanded, setExpanded] = useState(() => new Set());
  const [loading, setLoading] = useState(true);
  const containerRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  // Track container size
  useEffect(() => {
    const update = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  // Fetch context and build initial graph
  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(
          `http://localhost:3001/api/files/context?path=${encodeURIComponent(file.path)}`
        );
        const data = await res.json();
        const graph = buildInitialGraph(file, data);
        setGraphData(graph);
      } catch (err) {
        console.error('Failed to load graph context:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [file]);

  // Setup lighting + physics once graph is loaded
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || loading) return;

    const scene = fg.scene();

    // Clear old lights to avoid stacking
    scene.children
      .filter(c => c.isLight)
      .forEach(l => scene.remove(l));

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dir = new THREE.DirectionalLight(0xffffff, 0.8);
    dir.position.set(80, 140, 80);
    scene.add(dir);

    // Spaced-out physics
    fg.d3Force('charge').strength(-500);
    fg.d3Force('link').distance(180);
    if (typeof fg.d3VelocityDecay === 'function') {
      fg.d3VelocityDecay(0.2);
    }

    // Opening camera
    fg.cameraPosition({ x: 0, y: 0, z: 400 }, { x: 0, y: 0, z: 0 }, 1200);
  }, [loading]);

  // Node rendering
  const nodeThreeObject = useCallback((node) => {
    const color = colorByCategory[node.category] || colorByCategory.other;
    const radius = 7 + (node.score ?? 0.45) * 18;

    const geom = new THREE.SphereGeometry(radius, 24, 24);
    const mat = new THREE.MeshStandardMaterial({
      color,
      emissive: new THREE.Color(color),
      emissiveIntensity: node.isCenter ? 0.7 : 0.4,
      roughness: 0.5,
      metalness: 0.15,
    });
    const sphere = new THREE.Mesh(geom, mat);

    const halo = makeHaloSprite(color);
    halo.scale.set(radius * 6.5, radius * 6.5, 1);

    const label = makeTextSprite(node.label || node.id, {
      fontsize: 40,
      textColor: '#F0F0F0',
      borderColor: 'rgba(253,208,0,0.15)',
      backgroundColor: 'rgba(31,40,75,0.75)',
    });
    label.position.set(0, radius + 12, 0);

    const group = new THREE.Group();
    group.add(halo);
    group.add(sphere);
    group.add(label);
    return group;
  }, []);

  // Click to focus + expand
  const onNodeClick = useCallback(async (node) => {
    setSelected(node);

    const fg = fgRef.current;
    if (!fg) return;

    const distance = 200;
    const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);
    fg.cameraPosition(
      { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
      node,
      900
    );

    // Expand only once per node
    if (expanded.has(node.id) || node.isCenter) return;
    setExpanded(prev => new Set(prev).add(node.id));

    // Fetch context for this node if it has a file path
    if (node.filePath) {
      try {
        const res = await fetch(
          `http://localhost:3001/api/files/context?path=${encodeURIComponent(node.filePath)}`
        );
        const data = await res.json();
        const expansion = buildExpansionFromContext(node.id, data);
        setGraphData(g => mergeGraph(g, expansion.nodes, expansion.links));
      } catch {
        // If fetch fails, add generic expansion
        const expansion = buildGenericExpansion(node.id, node.category);
        setGraphData(g => mergeGraph(g, expansion.nodes, expansion.links));
      }
    } else {
      const expansion = buildGenericExpansion(node.id, node.category);
      setGraphData(g => mergeGraph(g, expansion.nodes, expansion.links));
    }
  }, [expanded]);

  if (loading) {
    return (
      <div className="graph-view">
        <div className="graph-loading">
          <div className="loading-dots"><span></span><span></span><span></span></div>
          <div className="graph-loading-text">Building graph...</div>
        </div>
        <button className="graph-back-btn" onClick={onBack}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Back
        </button>
      </div>
    );
  }

  return (
    <div className="graph-view" ref={containerRef}>
      {/* Back button */}
      <button className="graph-back-btn" onClick={onBack}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
        Back
      </button>

      {/* Graph */}
      {dimensions.width > 0 && (
        <ForceGraph3D
          ref={fgRef}
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="rgba(0,0,0,0)"
          nodeThreeObject={nodeThreeObject}
          nodeLabel={n => `${n.category?.toUpperCase()}\n${n.label || n.id}`}
          onNodeClick={onNodeClick}
          enableNodeDrag={true}
          showNavInfo={false}
          nodeRelSize={8}
          linkOpacity={0.2}
          linkWidth={l => 0.5 + (l.confidence ?? 0.5) * 2}
          linkColor={l => l.type === 'IN_FOLDER' ? 'rgba(76,201,240,0.4)' : 'rgba(253,208,0,0.3)'}
          linkDirectionalParticles={l => l.type === 'IN_FOLDER' ? 2 : 1}
          linkDirectionalParticleWidth={1.5}
          linkDirectionalParticleSpeed={0.006}
          linkDirectionalParticleColor={l => l.type === 'IN_FOLDER' ? '#4CC9F0' : '#FDD000'}
        />
      )}

      {/* Bottom-left info */}
      <div className="graph-info">
        <div className="graph-info-title">File Graph</div>
        <div className="graph-info-sub">Click nodes to expand &bull; Drag to orbit &bull; Scroll to zoom</div>
      </div>

      {/* Detail panel */}
      {selected && (
        <div className="graph-detail">
          <div className="graph-detail-category" style={{ color: colorByCategory[selected.category] || '#94A3B8' }}>
            {(selected.category || 'file').toUpperCase()}
          </div>
          <div className="graph-detail-name">{selected.label || selected.id}</div>
          {selected.description && (
            <div className="graph-detail-desc">{selected.description}</div>
          )}
          <div className="graph-detail-meta">
            {selected.fileSize && <span>{formatSize(selected.fileSize)}</span>}
            {selected.filePath && <span className="graph-detail-path">{selected.filePath}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---- Graph builders ---- */

function buildInitialGraph(file, contextData) {
  const nodes = [];
  const links = [];
  const { parentDir, siblings, related } = contextData;

  // Central node (the clicked file)
  nodes.push({
    id: `file:${file.path}`,
    label: file.name,
    category: file.category,
    score: 1.0,
    isCenter: true,
    description: file.description,
    filePath: file.path,
    fileSize: file.size,
  });

  // Parent folder node
  if (parentDir !== undefined) {
    const folderName = parentDir ? parentDir.split('\\').pop().split('/').pop() : 'Root';
    const folderId = `folder:${parentDir || 'root'}`;
    nodes.push({
      id: folderId,
      label: folderName,
      category: 'folder',
      score: 0.65,
      description: `Parent directory containing ${file.name}`,
      filePath: null,
    });
    links.push({
      source: `file:${file.path}`,
      target: folderId,
      type: 'IN_FOLDER',
      confidence: 0.9,
    });

    // Sibling files
    for (const sib of siblings) {
      const sibId = `file:${sib.path}`;
      nodes.push({
        id: sibId,
        label: sib.name,
        category: sib.category,
        score: 0.35 + Math.random() * 0.25,
        description: sib.description,
        filePath: sib.path,
        fileSize: sib.size,
      });
      links.push({
        source: folderId,
        target: sibId,
        type: 'IN_FOLDER',
        confidence: 0.7 + Math.random() * 0.2,
      });
    }
  }

  // Related files (same category, different folder)
  for (const rel of related) {
    const relId = `file:${rel.path}`;
    nodes.push({
      id: relId,
      label: rel.name,
      category: rel.category,
      score: 0.3 + Math.random() * 0.25,
      description: rel.description,
      filePath: rel.path,
      fileSize: rel.size,
    });
    links.push({
      source: `file:${file.path}`,
      target: relId,
      type: 'RELATED_BY',
      confidence: 0.4 + Math.random() * 0.35,
    });
  }

  return { nodes, links };
}

function buildExpansionFromContext(nodeId, contextData) {
  const nodes = [];
  const links = [];
  const { parentDir, siblings, related } = contextData;

  // Add a few siblings
  const sibSlice = siblings.slice(0, 4);
  for (const sib of sibSlice) {
    const sibId = `file:${sib.path}`;
    nodes.push({
      id: sibId,
      label: sib.name,
      category: sib.category,
      score: 0.3 + Math.random() * 0.2,
      description: sib.description,
      filePath: sib.path,
      fileSize: sib.size,
    });
    links.push({
      source: nodeId,
      target: sibId,
      type: 'IN_FOLDER',
      confidence: 0.6 + Math.random() * 0.2,
    });
  }

  // Add a couple related
  const relSlice = related.slice(0, 3);
  for (const rel of relSlice) {
    const relId = `file:${rel.path}`;
    nodes.push({
      id: relId,
      label: rel.name,
      category: rel.category,
      score: 0.25 + Math.random() * 0.2,
      description: rel.description,
      filePath: rel.path,
      fileSize: rel.size,
    });
    links.push({
      source: nodeId,
      target: relId,
      type: 'RELATED_BY',
      confidence: 0.4 + Math.random() * 0.3,
    });
  }

  return { nodes, links };
}

function buildGenericExpansion(nodeId, category) {
  const stamp = Math.random().toString(16).slice(2, 7);
  const nodes = [];
  const links = [];

  const n1 = {
    id: `meta:${stamp}:1`,
    label: `Metadata: ${category || 'unknown'}`,
    category: 'other',
    score: 0.35,
    description: `Metadata properties for this ${category} file`,
  };
  nodes.push(n1);
  links.push({
    source: nodeId,
    target: n1.id,
    type: 'HAS_METADATA',
    confidence: 0.8,
  });

  return { nodes, links };
}

/* ---- Graph merge (dedup) ---- */

function mergeGraph(current, newNodes, newLinks) {
  const nodeMap = new Map(current.nodes.map(n => [n.id, n]));
  newNodes.forEach(n => { if (!nodeMap.has(n.id)) nodeMap.set(n.id, n); });

  const linkKey = l => {
    const s = typeof l.source === 'object' ? l.source.id : String(l.source);
    const t = typeof l.target === 'object' ? l.target.id : String(l.target);
    return `${s}__${l.type}__${t}`;
  };
  const linkMap = new Map(current.links.map(l => [linkKey(l), l]));
  newLinks.forEach(l => { if (!linkMap.has(linkKey(l))) linkMap.set(linkKey(l), l); });

  return { nodes: Array.from(nodeMap.values()), links: Array.from(linkMap.values()) };
}

/* ---- Three.js visual helpers ---- */

function makeHaloSprite(color) {
  const canvas = document.createElement('canvas');
  const size = 256;
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');

  const grd = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grd.addColorStop(0, 'rgba(255,255,255,0.5)');
  grd.addColorStop(0.2, hexToRgba(color, 0.3));
  grd.addColorStop(0.45, hexToRgba(color, 0.12));
  grd.addColorStop(1, 'rgba(0,0,0,0)');

  ctx.fillStyle = grd;
  ctx.fillRect(0, 0, size, size);

  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
  return new THREE.Sprite(material);
}

function makeTextSprite(message, opts = {}) {
  const {
    fontsize = 44,
    textColor = '#ffffff',
    borderColor = 'rgba(255,255,255,0.12)',
    backgroundColor = 'rgba(0,0,0,0.4)',
    padding = 14,
  } = opts;

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');

  ctx.font = `${fontsize}px system-ui`;
  const textWidth = ctx.measureText(message).width;

  canvas.width = Math.ceil(textWidth + padding * 2);
  canvas.height = Math.ceil(fontsize + padding * 2);

  ctx.fillStyle = backgroundColor;
  roundRect(ctx, 0, 0, canvas.width, canvas.height, 12);
  ctx.fill();

  ctx.strokeStyle = borderColor;
  ctx.lineWidth = 2;
  roundRect(ctx, 1, 1, canvas.width - 2, canvas.height - 2, 12);
  ctx.stroke();

  ctx.font = `${fontsize}px system-ui`;
  ctx.fillStyle = textColor;
  ctx.textBaseline = 'middle';
  ctx.fillText(message, padding, canvas.height / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;

  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
  const sprite = new THREE.Sprite(material);

  const scale = 0.3;
  sprite.scale.set(canvas.width * scale, canvas.height * scale, 1);
  return sprite;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function hexToRgba(hex, a) {
  const h = hex.replace('#', '');
  const bigint = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16);
  const r = (bigint >> 16) & 255;
  const g = (bigint >> 8) & 255;
  const b = bigint & 255;
  return `rgba(${r},${g},${b},${a})`;
}
