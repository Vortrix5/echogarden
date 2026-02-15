import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import * as THREE from 'three';

// Node colors per spec
const COLORS = {
    Memory: '#FFD166',
    Person: '#4CC9F0',
    Topic: '#B5179E',
    Document: '#06D6A0',
    Conversation: '#8B5CF6',
    Platform: '#F72585',
    Time: '#FF6B6B',
    Evidence: '#94A3B8',
    default: '#cccccc'
};

// Hardcoded "Hackathon" data
const INITIAL_DATA = {
    nodes: [
        { id: 'root', label: 'Hackathon Memory', type: 'Memory', val: 20, description: 'Central node for the hackathon project memory' },
        { id: 'p1', label: 'Alice', type: 'Person', val: 10, description: 'Team Lead' },
        { id: 'p2', label: 'Bob', type: 'Person', val: 10, description: 'Frontend Dev' },
        { id: 't1', label: 'React', type: 'Topic', val: 8, description: 'Frontend Framework' },
        { id: 't2', label: 'Three.js', type: 'Topic', val: 8, description: '3D Library' },
        { id: 'd1', label: 'Spec.pdf', type: 'Document', val: 5, description: 'Project Requirements' },
        { id: 'c1', label: 'Kickoff Call', type: 'Conversation', val: 5, description: 'Initial team meeting' }
    ],
    links: [
        { source: 'root', target: 'p1', confidence: 0.9 },
        { source: 'root', target: 'p2', confidence: 0.9 },
        { source: 'root', target: 't1', confidence: 0.8 },
        { source: 'root', target: 't2', confidence: 0.8 },
        { source: 'root', target: 'd1', confidence: 0.7 },
        { source: 'root', target: 'c1', confidence: 0.6 }
    ]
};

export default function MemoryGraph3D({ onBack }) {
    const fgRef = useRef();
    const [graphData, setGraphData] = useState(INITIAL_DATA);
    const [selectedNode, setSelectedNode] = useState(null);
    const containerRef = useRef();
    const [dimensions, setDimensions] = useState({ width: window.innerWidth, height: window.innerHeight });

    // Handle Resize
    useEffect(() => {
        const updateSize = () => {
            if (containerRef.current) {
                setDimensions({
                    width: containerRef.current.clientWidth,
                    height: containerRef.current.clientHeight
                });
            }
        };
        window.addEventListener('resize', updateSize);
        updateSize();
        return () => window.removeEventListener('resize', updateSize);
    }, []);

    // Configure Physics & Lights
    useEffect(() => {
        const fg = fgRef.current;
        if (!fg) return;

        // Physics settings from spec
        // charge force -420 (repulsion), link distance 150, velocity decay 0.22
        fg.d3Force('charge').strength(-420);
        fg.d3Force('link').distance(150);
        if (typeof fg.d3VelocityDecay === 'function') {
            fg.d3VelocityDecay(0.22);
        }

        // Lighting
        const scene = fg.scene();
        // Clear existing lights to avoid buildup if this effect re-runs
        scene.children.filter(obj => obj.isLight).forEach(l => scene.remove(l));

        const ambient = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambient);

        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight.position.set(100, 100, 100);
        scene.add(dirLight);

    }, []);

    const handleNodeClick = useCallback(node => {
        setSelectedNode(node);

        // Camera focus
        const distance = 200;
        const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);

        fgRef.current.cameraPosition(
            { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio }, // new position
            node, // lookAt ({ x, y, z })
            2000  // ms transition duration
        );

        // "Expand" logic (mocked for demo as one-time expansion)
        // In a real app this would fetch data. Here we just add dummy nodes if not already expanded.
        // For now, keeping it static as per "Hardcoded hackathon data" description to start.

    }, []);

    // Node Object Customization
    const nodeThreeObject = useCallback(node => {
        const color = COLORS[node.type] || COLORS.default;
        const radius = 5 + (node.val || 1) * 0.5;

        // Glowing 3D sphere
        const geometry = new THREE.SphereGeometry(radius, 32, 32);
        const material = new THREE.MeshStandardMaterial({
            color: color,
            emissive: color,
            emissiveIntensity: 0.6,
            roughness: 0.4,
            metalness: 0.1
        });
        const sphere = new THREE.Mesh(geometry, material);

        // Halo Sprite
        const halo = makeHaloSprite(color);
        halo.scale.set(radius * 8, radius * 8, 1);

        // Text Label Sprite
        const label = makeTextSprite(node.label, { color: color });
        label.position.set(0, radius + 10, 0);

        const group = new THREE.Group();
        group.add(halo);
        group.add(sphere);
        group.add(label);

        return group;
    }, []);

    return (
        <div style={{ position: 'relative', width: '100%', height: '100%' }} ref={containerRef}>
            {/* Back / Toggle Button (handled by parent usually, but adding a local back for safety) */}
            {onBack && (
                <button
                    onClick={onBack}
                    style={{
                        position: 'absolute', top: 20, left: 20, zIndex: 10,
                        background: 'rgba(0,0,0,0.5)', color: 'white', border: '1px solid white',
                        padding: '8px 16px', borderRadius: '4px', cursor: 'pointer'
                    }}
                >
                    Back
                </button>
            )}

            {/* Side Panel */}
            {selectedNode && (
                <div style={{
                    position: 'absolute', top: 20, right: 20, width: 300,
                    background: 'rgba(15, 23, 42, 0.9)', color: 'white',
                    padding: '20px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)',
                    backdropFilter: 'blur(10px)', zIndex: 5
                }}>
                    <h2 style={{ margin: '0 0 10px 0', color: COLORS[selectedNode.type] || 'white' }}>
                        {selectedNode.type.toUpperCase()}
                    </h2>
                    <h3 style={{ margin: '0 0 10px 0', fontSize: '1.2rem' }}>{selectedNode.label}</h3>
                    <p style={{ lineHeight: '1.5', color: '#cbd5e1' }}>{selectedNode.description}</p>
                    <div style={{ marginTop: '15px', fontSize: '0.9rem', color: '#94a3b8' }}>
                        ID: {selectedNode.id}
                    </div>
                    <button
                        onClick={() => setSelectedNode(null)}
                        style={{
                            marginTop: '15px', background: 'transparent', border: '1px solid #475569',
                            color: '#cbd5e1', padding: '5px 10px', borderRadius: '4px', cursor: 'pointer'
                        }}
                    >
                        Close
                    </button>
                </div>
            )}

            <ForceGraph3D
                ref={fgRef}
                width={dimensions.width}
                height={dimensions.height}
                graphData={graphData}
                backgroundColor="#000000"
                nodeThreeObject={nodeThreeObject}
                nodeLabel="label"
                // Link styling
                linkColor={() => '#ffffff'}
                linkOpacity={0.2}
                linkWidth={1}
                linkDirectionalParticles={2}
                linkDirectionalParticleSpeed={0.005}
                linkDirectionalParticleWidth={1.5}
                onNodeClick={handleNodeClick}
            />
        </div>
    );
}

// --- VISUAL HELPERS (Adapted from previous GraphView) ---

function makeHaloSprite(color) {
    const canvas = document.createElement('canvas');
    const size = 256;
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');

    const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    gradient.addColorStop(0, hexToRgba(color, 0.4));
    gradient.addColorStop(0.5, hexToRgba(color, 0.1));
    gradient.addColorStop(1, 'rgba(0,0,0,0)');

    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);

    const texture = new THREE.CanvasTexture(canvas);
    const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    return new THREE.Sprite(material);
}

function makeTextSprite(text, { color = '#ffffff' } = {}) {
    const canvas = document.createElement('canvas');
    const fontSize = 48; // High res for scaling down
    const padding = 10;

    const ctx = canvas.getContext('2d');
    ctx.font = `bold ${fontSize}px Sans-Serif`;
    const textWidth = ctx.measureText(text).width;

    canvas.width = textWidth + padding * 2;
    canvas.height = fontSize + padding * 2;

    // Re-set context after resizing
    ctx.font = `bold ${fontSize}px Sans-Serif`;
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)'; // Background
    roundRect(ctx, 0, 0, canvas.width, canvas.height, 10);
    ctx.fill();

    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);

    const texture = new THREE.CanvasTexture(canvas);
    const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
    const sprite = new THREE.Sprite(material);

    // Scale down to reasonable size in 3D world
    sprite.scale.set(canvas.width * 0.2, canvas.height * 0.2, 1);
    return sprite;
}

function hexToRgba(hex, alpha = 1) {
    // Simple hex to rgba conversion
    let c;
    if (/^#([A-Fa-f0-9]{3}){1,2}$/.test(hex)) {
        c = hex.substring(1).split('');
        if (c.length == 3) {
            c = [c[0], c[0], c[1], c[1], c[2], c[2]];
        }
        c = '0x' + c.join('');
        return 'rgba(' + [(c >> 16) & 255, (c >> 8) & 255, c & 255].join(',') + ',' + alpha + ')';
    }
    return `rgba(255,255,255,${alpha})`;
}

function roundRect(ctx, x, y, w, h, r) {
    if (w < 2 * r) r = w / 2;
    if (h < 2 * r) r = h / 2;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
}
