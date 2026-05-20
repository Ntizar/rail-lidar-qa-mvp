import * as THREE from './vendor/three.module.js';

const viewer = document.getElementById('viewer');
const viewerStatus = document.getElementById('viewerStatus');
const fileSelect = document.getElementById('fileSelect');
const sampleInput = document.getElementById('sampleInput');
const gridInput = document.getElementById('gridInput');
const lengthInput = document.getElementById('lengthInput');
const widthInput = document.getElementById('widthInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const animateBtn = document.getElementById('animateBtn');
const qaToggleBtn = document.getElementById('qaToggleBtn');
const reportBtn = document.getElementById('reportBtn');
const resetViewBtn = document.getElementById('resetViewBtn');
const passCount = document.getElementById('passCount');
const passList = document.getElementById('passList');
const qaLamp = document.getElementById('qaLamp');
const qaTitle = document.getElementById('qaTitle');
const qaSubtitle = document.getElementById('qaSubtitle');
const qaScore = document.getElementById('qaScore');
const metricList = document.getElementById('metricList');
const modelFormula = document.getElementById('modelFormula');
const railModelText = document.getElementById('railModelText');
const gnssText = document.getElementById('gnssText');
const reportSummary = document.getElementById('reportSummary');
const semanticLegend = document.getElementById('semanticLegend');

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xdce6e2);
scene.fog = new THREE.Fog(0xdce6e2, 650, 1600);

const camera = new THREE.PerspectiveCamera(58, 1, 0.1, 2000);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
viewer.appendChild(renderer.domElement);

const ambient = new THREE.HemisphereLight(0xffffff, 0x71807b, 1.8);
scene.add(ambient);

const sun = new THREE.DirectionalLight(0xffffff, 1.8);
sun.position.set(80, 140, 60);
sun.castShadow = true;
scene.add(sun);

const rootGroup = new THREE.Group();
const pointGroup = new THREE.Group();
const gridGroup = new THREE.Group();
const pathGroup = new THREE.Group();
const droneGroup = new THREE.Group();
const droneDensityGroup = new THREE.Group();
const railGroup = new THREE.Group();
const railSectionGroup = new THREE.Group();
const tamperGroup = new THREE.Group();
const anomalyGroup = new THREE.Group();
scene.add(rootGroup, gridGroup, pathGroup, droneGroup, droneDensityGroup, railGroup, railSectionGroup, tamperGroup, anomalyGroup);
rootGroup.add(pointGroup);

const controls = {
  target: new THREE.Vector3(0, 8, 0),
  distance: 115,
  yaw: -0.75,
  pitch: 0.82,
  dragging: false,
  lastX: 0,
  lastY: 0,
};

let currentData = null;
let dronesAnimating = false;
let qaVisible = true;
let operationStart = 0;
const clock = new THREE.Clock();

const qaColors = {
  green: 0x1b8f5a,
  yellow: 0xd99212,
  red: 0xc33a2b,
};

init();

async function init() {
  setupEvents();
  resizeRenderer();
  createGroundPlane();
  createRailOverlay(200, 80);
  await loadFiles();
  animate();
}

function setupEvents() {
  window.addEventListener('resize', resizeRenderer);
  analyzeBtn.addEventListener('click', analyzeCurrentFile);
  animateBtn.addEventListener('click', () => {
    dronesAnimating = !dronesAnimating;
    animateBtn.textContent = dronesAnimating ? 'Pausar drones' : 'Animar pasadas';
  });
  qaToggleBtn.addEventListener('click', () => {
    qaVisible = !qaVisible;
    gridGroup.visible = qaVisible;
    qaToggleBtn.textContent = qaVisible ? 'QA visible' : 'QA oculto';
  });
  reportBtn.addEventListener('click', () => {
    const reportUrl = fileSelect.dataset.staticMode === 'true' ? './informe_qa.html' : '/api/report';
    window.open(reportUrl, '_blank', 'noopener');
  });
  resetViewBtn.addEventListener('click', () => {
    if (currentData) frameScene(currentData.metrics.roi.length, currentData.metrics.roi.width, currentData.metrics.zRange);
  });
  passCount.addEventListener('change', () => {
    drawPathsAndDrones(currentData?.paths ?? []);
    renderPassList(currentData?.paths ?? []);
  });

  renderer.domElement.addEventListener('pointerdown', (event) => {
    controls.dragging = true;
    controls.lastX = event.clientX;
    controls.lastY = event.clientY;
    renderer.domElement.setPointerCapture(event.pointerId);
  });
  renderer.domElement.addEventListener('pointermove', (event) => {
    if (!controls.dragging) return;
    const dx = event.clientX - controls.lastX;
    const dy = event.clientY - controls.lastY;
    controls.lastX = event.clientX;
    controls.lastY = event.clientY;
    controls.yaw -= dx * 0.006;
    controls.pitch = Math.max(0.18, Math.min(1.34, controls.pitch + dy * 0.004));
  });
  renderer.domElement.addEventListener('pointerup', (event) => {
    controls.dragging = false;
    renderer.domElement.releasePointerCapture(event.pointerId);
  });
  renderer.domElement.addEventListener('wheel', (event) => {
    event.preventDefault();
    controls.distance = Math.max(28, Math.min(360, controls.distance + event.deltaY * 0.08));
  }, { passive: false });
}

async function loadFiles() {
  setStatus('Buscando archivos LAZ/LAS en la carpeta del proyecto...');
  let payload;
  if (isStaticDeployment()) {
    payload = { files: ['sample_analysis.json'], default: 'sample_analysis.json', staticMode: true };
  } else {
    try {
    const response = await fetch('/api/files');
    if (!response.ok) throw new Error('API no disponible');
    payload = await response.json();
    } catch {
      payload = { files: ['sample_analysis.json'], default: 'sample_analysis.json', staticMode: true };
    }
  }
  fileSelect.innerHTML = '';
  for (const file of payload.files) {
    const option = document.createElement('option');
    option.value = file;
    option.textContent = file;
    option.selected = file === payload.default;
    fileSelect.appendChild(option);
  }
  fileSelect.dataset.staticMode = payload.staticMode ? 'true' : 'false';
  if (!payload.files.length) {
    setStatus('No se encontro ningun archivo .laz o .las en la raiz del proyecto.');
    return;
  }
  setStatus(payload.staticMode ? 'Demo estatica lista. Pulsa Analizar LAZ para cargar el gemelo preprocesado.' : 'Archivo detectado. Pulsa Analizar LAZ para generar el gemelo digital QA.');
}

function isStaticDeployment() {
  return location.hostname.endsWith('github.io') || location.hostname.endsWith('vercel.app') || location.port === '9000';
}

async function analyzeCurrentFile() {
  if (!fileSelect.value) return;
  setBusy(true, 'Procesando LAZ por chunks. La primera carga puede tardar unos segundos...');
  const params = new URLSearchParams({
    file: fileSelect.value,
    sample: sampleInput.value,
    grid: gridInput.value,
    length: lengthInput.value,
    width: widthInput.value,
  });
  try {
    const endpoint = fileSelect.dataset.staticMode === 'true' ? './sample_analysis.json' : `/api/analyze?${params.toString()}`;
    const response = await fetch(endpoint);
    const payload = await response.json();
    if (!response.ok || payload.error) {
      throw new Error(payload.error ?? 'No se pudo analizar el archivo');
    }
    currentData = payload;
    drawScene(payload);
    updateMetrics(payload.metrics);
    setStatus(`Analisis listo: ${formatNumber(payload.metrics.samplePointCount)} puntos en vista, ${formatNumber(payload.metrics.roiPointCount)} puntos en la zona de control.`);
  } catch (error) {
    setStatus(`Error: ${error.message}`);
  } finally {
    setBusy(false);
  }
}

function drawScene(data) {
  clearGroup(pointGroup);
  clearGroup(gridGroup);
  clearGroup(pathGroup);
  clearGroup(droneGroup);
  clearGroup(droneDensityGroup);
  clearGroup(railGroup);
  clearGroup(railSectionGroup);
  clearGroup(tamperGroup);
  clearGroup(anomalyGroup);

  createPointCloud(data.points);
  createGrid(data.grid);
  createRailOverlay(data.metrics.roi.length, data.metrics.roi.width, data.track?.railModel);
  createRailCrossSection(data.track?.railModel?.crossSection);
  createDroneDensity(data.droneDensity);
  createTamper(data.tamping);
  createAnomalyMarker(data.metrics.anomaly);
  drawPathsAndDrones(data.paths);
  renderPassList(data.paths);
  updateProfessionalPanels(data);
  frameScene(data.metrics.roi.length, data.metrics.roi.width, data.metrics.zRange);
}

function createPointCloud(points) {
  const positions = new Float32Array(points.length * 3);
  const colors = new Float32Array(points.length * 3);
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index];
    positions[index * 3] = point[0];
    positions[index * 3 + 1] = point[1] * 1.35;
    positions[index * 3 + 2] = point[2];
    colors[index * 3] = point[3] / 255;
    colors[index * 3 + 1] = point[4] / 255;
    colors[index * 3 + 2] = point[5] / 255;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.computeBoundingSphere();
  const material = new THREE.PointsMaterial({ size: 0.42, vertexColors: true, sizeAttenuation: true });
  const cloud = new THREE.Points(geometry, material);
  pointGroup.add(cloud);
}

function createGrid(cells) {
  const geometry = new THREE.PlaneGeometry(1, 1);
  for (const cell of cells) {
    const material = new THREE.MeshBasicMaterial({
      color: colorForError(cell.beforeErrorMm),
      transparent: true,
      opacity: cell.anomaly ? 0.62 : 0.34,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.scale.set(cell.width, cell.depth, 1);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(cell.x, cell.y * 1.35 + 0.08, cell.z);
    mesh.userData = cell;
    gridGroup.add(mesh);
  }
  gridGroup.visible = qaVisible;
}

function createTamper(tamping) {
  if (!tamping?.path?.length) return;
  const group = new THREE.Group();
  const bodyMaterial = new THREE.MeshStandardMaterial({ color: 0x176f5d, roughness: 0.55, metalness: 0.12 });
  const cabinMaterial = new THREE.MeshStandardMaterial({ color: 0xf4c95d, roughness: 0.42, metalness: 0.08 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(7.5, 1.45, 2.25), bodyMaterial);
  body.position.y = 1.1;
  const cabin = new THREE.Mesh(new THREE.BoxGeometry(2.2, 1.35, 1.9), cabinMaterial);
  cabin.position.set(-1.6, 2.15, 0);
  group.add(body, cabin);
  for (const x of [-2.7, 2.7]) {
    for (const z of [-0.82, 0.82]) {
      const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 0.22, 24), new THREE.MeshStandardMaterial({ color: 0x252b29 }));
      wheel.rotation.z = Math.PI / 2;
      wheel.position.set(x, 0.42, z);
      group.add(wheel);
    }
  }
  group.userData.path = tamping.path.map((point) => new THREE.Vector3(point[0], point[1] * 1.35, point[2]));
  tamperGroup.add(group);
}

function createAnomalyMarker(anomaly) {
  if (!anomaly) return;
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(anomaly.radiusM, anomaly.radiusM + 0.45, 48),
    new THREE.MeshBasicMaterial({ color: 0xc33a2b, transparent: true, opacity: 0.85, side: THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.set(anomaly.alongM, 0.55, anomaly.crossM);
  anomalyGroup.add(ring);
}

function createRailOverlay(length, width, railModel = null) {
  const railLength = Math.max(length, 20);
  const sleeperCount = Math.max(12, Math.min(260, Math.floor(railLength / 4)));
  const profile = railModel?.profile?.length ? railModel.profile : fallbackRailProfile(railLength);
  const gauge = railModel?.gaugeM ?? 1.435;
  const crossCenter = railModel?.crossCenterM ?? 0;
  const sleeperLength = railModel?.sleeperLengthM ?? 2.6;
  const railMaterial = new THREE.MeshStandardMaterial({ color: 0x313836, roughness: 0.7, metalness: 0.18 });
  const sleeperMaterial = new THREE.MeshStandardMaterial({ color: 0x7b7067, roughness: 0.9 });

  const ballastStrip = new THREE.Mesh(
    new THREE.PlaneGeometry(railLength, Math.max(5.5, sleeperLength + 2.4)),
    new THREE.MeshBasicMaterial({ color: 0xb69a62, transparent: true, opacity: 0.26, side: THREE.DoubleSide })
  );
  ballastStrip.rotation.x = -Math.PI / 2;
  ballastStrip.position.set(0, profileY(profile, 0) + 0.05, crossCenter);
  railGroup.add(ballastStrip);

  for (const offset of [-gauge / 2, gauge / 2]) {
    const curvePoints = profile.map((point) => toRailVector(point, offset));
    const curve = new THREE.CatmullRomCurve3(curvePoints);
    const rail = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(32, profile.length * 3), 0.07, 8, false), railMaterial);
    rail.castShadow = true;
    railGroup.add(rail);
  }

  const sleeperGeometry = new THREE.BoxGeometry(0.24, 0.12, sleeperLength);
  for (let i = 0; i < sleeperCount; i += 1) {
    const sleeper = new THREE.Mesh(sleeperGeometry, sleeperMaterial);
    const along = -railLength / 2 + i * (railLength / Math.max(sleeperCount - 1, 1));
    const center = profilePoint(profile, along);
    sleeper.position.set(along, center[1] * 1.35 + 0.04, center[2]);
    railGroup.add(sleeper);
  }
  const corridorMaterial = new THREE.LineBasicMaterial({ color: 0x49534f, transparent: true, opacity: 0.55 });
  const halfL = length / 2;
  const halfW = width / 2;
  const points = [
    new THREE.Vector3(-halfL, 0.05, -halfW),
    new THREE.Vector3(halfL, 0.05, -halfW),
    new THREE.Vector3(halfL, 0.05, halfW),
    new THREE.Vector3(-halfL, 0.05, halfW),
    new THREE.Vector3(-halfL, 0.05, -halfW),
  ];
  const corridor = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), corridorMaterial);
  railGroup.add(corridor);
}

function createRailCrossSection(crossSection) {
  if (!crossSection?.terrain?.length) return;
  const station = crossSection.stationM ?? 0;
  const center = crossSection.centerCrossM ?? 0;
  const terrainPoints = crossSection.terrain.map((point) => new THREE.Vector3(station, point[1] * 1.35 + 0.07, point[0]));
  const terrainCurve = new THREE.CatmullRomCurve3(terrainPoints);
  const terrainTube = new THREE.Mesh(
    new THREE.TubeGeometry(terrainCurve, Math.max(24, terrainPoints.length * 2), 0.09, 8, false),
    new THREE.MeshBasicMaterial({ color: 0x00a84f })
  );
  railSectionGroup.add(terrainTube);

  const slicePlane = new THREE.Mesh(
    new THREE.PlaneGeometry(0.08, Math.max(24, Math.abs(crossSection.terrain.at(-1)[0] - crossSection.terrain[0][0]))),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.18, side: THREE.DoubleSide })
  );
  slicePlane.rotation.y = Math.PI / 2;
  slicePlane.position.set(station, Math.max(6, crossSection.layers[0].topY * 1.35 - 2.5), center);
  railSectionGroup.add(slicePlane);

  for (const layer of [...crossSection.layers].reverse()) {
    const mesh = createLayerPrism(station, center, layer);
    railSectionGroup.add(mesh);
  }

  const markerMaterial = new THREE.LineDashedMaterial({ color: 0x111111, dashSize: 0.9, gapSize: 0.5 });
  const marker = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(station, profileY([[station, crossSection.layers[0].topY, center]], station) - 5, center),
      new THREE.Vector3(station, profileY([[station, crossSection.layers[0].topY, center]], station) + 10, center),
    ]),
    markerMaterial
  );
  marker.computeLineDistances();
  railSectionGroup.add(marker);
}

function createLayerPrism(station, center, layer) {
  const top = layer.topY * 1.35;
  const bottom = (layer.topY - layer.thicknessM) * 1.35;
  const topHalf = layer.topWidthM / 2;
  const bottomHalf = layer.bottomWidthM / 2;
  const halfDepth = 0.55;
  const vertices = new Float32Array([
    station - halfDepth, top, center - topHalf,
    station - halfDepth, top, center + topHalf,
    station - halfDepth, bottom, center + bottomHalf,
    station - halfDepth, bottom, center - bottomHalf,
    station + halfDepth, top, center - topHalf,
    station + halfDepth, top, center + topHalf,
    station + halfDepth, bottom, center + bottomHalf,
    station + halfDepth, bottom, center - bottomHalf,
  ]);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
  geometry.setIndex([
    0, 1, 2, 0, 2, 3,
    4, 7, 6, 4, 6, 5,
    0, 4, 5, 0, 5, 1,
    1, 5, 6, 1, 6, 2,
    2, 6, 7, 2, 7, 3,
    3, 7, 4, 3, 4, 0,
  ]);
  geometry.computeVertexNormals();
  return new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({ color: new THREE.Color(layer.color), transparent: true, opacity: 0.84, roughness: 0.72, side: THREE.DoubleSide })
  );
}

function createDroneDensity(density) {
  if (!density?.points?.length) return;
  const points = [...density.points].sort((a, b) => a[0] - b[0]);
  const positions = new Float32Array(points.length * 3);
  const colors = new Float32Array(points.length * 3);
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index];
    positions[index * 3] = point[0];
    positions[index * 3 + 1] = point[1] * 1.35;
    positions[index * 3 + 2] = point[2];
    colors[index * 3] = point[3] / 255;
    colors[index * 3 + 1] = point[4] / 255;
    colors[index * 3 + 2] = point[5] / 255;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.setDrawRange(0, 0);
  const cloud = new THREE.Points(geometry, new THREE.PointsMaterial({ size: 0.8, vertexColors: true, transparent: true, opacity: 0.92 }));
  cloud.userData.count = points.length;
  droneDensityGroup.add(cloud);
}

function fallbackRailProfile(length) {
  return Array.from({ length: 31 }, (_, index) => {
    const x = -length / 2 + (length * index) / 30;
    return [x, 0, 0];
  });
}

function profileY(profile, along) {
  return profilePoint(profile, along)[1] * 1.35 + 0.22;
}

function profilePoint(profile, along) {
  let nearest = profile[0];
  let best = Infinity;
  for (const point of profile) {
    const distance = Math.abs(point[0] - along);
    if (distance < best) {
      nearest = point;
      best = distance;
    }
  }
  return nearest;
}

function toRailVector(profilePoint, offset) {
  return new THREE.Vector3(profilePoint[0], profilePoint[1] * 1.35 + 0.32, profilePoint[2] + offset);
}

function drawPathsAndDrones(paths) {
  clearGroup(pathGroup);
  clearGroup(droneGroup);
  const count = Number(passCount.value);
  const visiblePaths = paths.slice(0, count);
  for (const path of visiblePaths) {
    const linePoints = path.points.map((point) => new THREE.Vector3(point[0], point[1], point[2]));
    const geometry = new THREE.BufferGeometry().setFromPoints(linePoints);
    const material = new THREE.LineBasicMaterial({ color: new THREE.Color(path.color), linewidth: 2 });
    const line = new THREE.Line(geometry, material);
    pathGroup.add(line);

    const drone = createDrone(path.color);
    drone.userData.path = linePoints;
    drone.userData.offset = path.id * 0.19;
    droneGroup.add(drone);
  }
}

function createDrone(color) {
  const group = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(1.2, 0.32, 0.8),
    new THREE.MeshStandardMaterial({ color: new THREE.Color(color), roughness: 0.45, metalness: 0.2 })
  );
  group.add(body);
  const armMaterial = new THREE.MeshStandardMaterial({ color: 0x202725, roughness: 0.55 });
  const armA = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.08, 0.08), armMaterial);
  const armB = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.08, 1.8), armMaterial);
  group.add(armA, armB);
  const rotorGeometry = new THREE.CylinderGeometry(0.25, 0.25, 0.04, 24);
  for (const x of [-1.05, 1.05]) {
    for (const z of [-0.9, 0.9]) {
      const rotor = new THREE.Mesh(rotorGeometry, armMaterial);
      rotor.position.set(x, 0.05, z);
      group.add(rotor);
    }
  }
  return group;
}

function updateMetrics(metrics) {
  const labels = {
    green: 'Aceptable',
    yellow: 'Revision',
    red: 'Repetir zonas',
  };
  qaLamp.className = `qa-lamp ${metrics.qaStatus}`;
  qaTitle.textContent = labels[metrics.qaStatus] ?? 'Analizado';
  qaSubtitle.textContent = `${formatNumber(metrics.qaCounts.green)} verdes, ${formatNumber(metrics.qaCounts.yellow)} amarillas, ${formatNumber(metrics.qaCounts.red)} rojas`;
  qaScore.textContent = `${metrics.qaScore}`;

  const rows = [
    ['Puntos totales', formatNumber(metrics.pointCount)],
    ['Puntos ROI', formatNumber(metrics.roiPointCount)],
    ['Muestra vista', formatNumber(metrics.samplePointCount)],
    ['Densidad media', `${metrics.densityM2} pts/m2`],
    ['Densidad ROI', `${metrics.roiDensityM2} pts/m2`],
    ['Rango Z', `${metrics.zRange} m`],
    ['Anomalia simulada', `${metrics.anomaly.alongM} m / ${metrics.anomaly.crossM} m`],
    ['Superficie tile', `${formatNumber(metrics.areaM2)} m2`],
    ['RGB disponible', metrics.hasRgb ? 'si' : 'no'],
  ];
  metricList.innerHTML = rows.map(([name, value]) => `<div class="metric-row"><dt>${name}</dt><dd>${value}</dd></div>`).join('');
}

function updateProfessionalPanels(data) {
  modelFormula.textContent = `${data.optimizer.formula}. Objetivo: ${data.optimizer.objective}. Ganancia estimada: ${data.optimizer.coverageGainPct}%.`;
  gnssText.textContent = `${data.gnss.sovereignty} Precision: ${data.gnss.absoluteAccuracy}. Repetibilidad: ${data.gnss.relativeRepeatability}.`;
  const density = data.droneDensity;
  const densityText = density ? ` Densidad local simulada: ${density.beforeDensityPtsM2} -> ${density.afterDensityPtsM2} pts/m2; error esperado ${density.accuracyBeforeMm} -> ${density.accuracyAfterMm} mm.` : '';
  reportSummary.textContent = `${data.report.recommendation}. ${data.metrics.anomaly.message}${densityText}`;
  const railModel = data.track?.railModel;
  railModelText.textContent = railModel
    ? `Centro transversal ${railModel.crossCenterM} m, ancho UIC ${railModel.gaugeM} m. Fuente: ${railModel.source}.`
    : 'No hay puntos suficientes para ajustar la via; se usa geometria auxiliar.';
  renderSemanticLegend(data.metrics.semanticStats ?? {});
}

function renderPassList(paths) {
  const count = Number(passCount.value);
  passList.innerHTML = paths.slice(0, count).map((path) => (
    `<div class="pass-item"><span class="pass-dot" style="background:${path.color}"></span><span><strong>${path.name}</strong><small>${path.objective ?? ''} · solape ${path.overlapPct ?? '--'}% · bateria ${path.batteryPct ?? '--'}% · residual ${Math.round((path.residualFactor ?? 1) * 100)}%</small></span></div>`
  )).join('');
}

function renderSemanticLegend(stats) {
  const entries = Object.entries(stats);
  if (!entries.length) {
    semanticLegend.innerHTML = '<p>La leyenda se calcula al analizar la nube.</p>';
    return;
  }
  semanticLegend.innerHTML = entries.map(([, item]) => (
    `<div class="semantic-row"><span class="semantic-swatch" style="background:${item.color}"></span><span>${item.label}<strong>${item.pct}%</strong></span></div>`
  )).join('');
}

function createGroundPlane() {
  const geometry = new THREE.PlaneGeometry(1800, 900, 1, 1);
  const material = new THREE.MeshStandardMaterial({ color: 0xcdd9d4, roughness: 0.95, metalness: 0.0 });
  const plane = new THREE.Mesh(geometry, material);
  plane.rotation.x = -Math.PI / 2;
  plane.position.y = -0.08;
  scene.add(plane);
}

function frameScene(length, width, zRange) {
  controls.target.set(0, Math.max(6, zRange * 0.5), 0);
  controls.distance = Math.max(90, Math.min(980, Math.max(length, width) * 1.08));
  controls.yaw = -0.72;
  controls.pitch = 0.78;
}

function animate() {
  requestAnimationFrame(animate);
  const elapsed = clock.getElapsedTime();
  updateCamera();
  if (dronesAnimating) {
    if (!operationStart) operationStart = elapsed;
    updateOperationalAnimation(elapsed - operationStart);
    updateDrones(elapsed);
  } else {
    operationStart = 0;
  }
  renderer.render(scene, camera);
}

function updateOperationalAnimation(elapsed) {
  const progress = (elapsed * 0.08) % 1;
  updateTamper(progress);
  updateGridError(progress);
  updateDroneDensity(progress);
}

function updateTamper(progress) {
  const tamper = tamperGroup.children[0];
  if (!tamper?.userData?.path) return;
  const position = samplePath(tamper.userData.path, progress);
  const next = samplePath(tamper.userData.path, Math.min(progress + 0.01, 1));
  tamper.position.copy(position);
  tamper.lookAt(next);
}

function updateGridError(progress) {
  if (!currentData?.metrics?.roi) return;
  const activeFront = -currentData.metrics.roi.length / 2 + currentData.metrics.roi.length * progress;
  for (const cellMesh of gridGroup.children) {
    const cell = cellMesh.userData;
    const localProgress = cell.x < activeFront ? Math.min(1, Math.max(0, (activeFront - cell.x) / 18)) : 0;
    const error = cell.beforeErrorMm + (cell.afterErrorMm - cell.beforeErrorMm) * localProgress;
    cellMesh.material.color.setHex(colorForError(error));
    cellMesh.material.opacity = cell.anomaly && localProgress > 0.6 ? 0.72 : 0.28 + localProgress * 0.16;
  }
}

function updateDroneDensity(progress) {
  const densityCloud = droneDensityGroup.children[0];
  if (!densityCloud?.geometry) return;
  const count = densityCloud.userData.count ?? 0;
  densityCloud.geometry.setDrawRange(0, Math.floor(count * progress));
}

function colorForError(errorMm) {
  if (errorMm <= 28) return qaColors.green;
  if (errorMm <= 55) return qaColors.yellow;
  return qaColors.red;
}

function updateCamera() {
  const x = controls.target.x + Math.cos(controls.yaw) * Math.cos(controls.pitch) * controls.distance;
  const y = controls.target.y + Math.sin(controls.pitch) * controls.distance;
  const z = controls.target.z + Math.sin(controls.yaw) * Math.cos(controls.pitch) * controls.distance;
  camera.position.set(x, y, z);
  camera.lookAt(controls.target);
}

function updateDrones(elapsed) {
  for (const drone of droneGroup.children) {
    const path = drone.userData.path;
    if (!path || path.length < 2) continue;
    const t = (elapsed * 0.08 + drone.userData.offset) % 1;
    const position = samplePath(path, t);
    const next = samplePath(path, (t + 0.01) % 1);
    drone.position.copy(position);
    drone.lookAt(next);
  }
}

function samplePath(points, t) {
  const segmentCount = points.length - 1;
  const scaled = t * segmentCount;
  const index = Math.min(Math.floor(scaled), segmentCount - 1);
  const localT = scaled - index;
  return new THREE.Vector3().lerpVectors(points[index], points[index + 1], localT);
}

function resizeRenderer() {
  const rect = viewer.getBoundingClientRect();
  renderer.setSize(rect.width, rect.height);
  camera.aspect = rect.width / Math.max(rect.height, 1);
  camera.updateProjectionMatrix();
}

function clearGroup(group) {
  while (group.children.length) {
    const child = group.children.pop();
    child.traverse?.((node) => {
      node.geometry?.dispose?.();
      if (Array.isArray(node.material)) {
        node.material.forEach((material) => material.dispose?.());
      } else {
        node.material?.dispose?.();
      }
    });
  }
}

function setBusy(isBusy, message = '') {
  analyzeBtn.disabled = isBusy;
  analyzeBtn.textContent = isBusy ? 'Analizando...' : 'Analizar LAZ';
  if (message) setStatus(message);
}

function setStatus(message) {
  viewerStatus.textContent = message;
}

function formatNumber(value) {
  return new Intl.NumberFormat('es-ES').format(value);
}
