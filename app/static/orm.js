/* Ormen som kryper över sidan när någon försöker peka en kortlänk på svky.se.
 *
 * Ritas bara när beställningssidan bett om det - se bestall.html. Den som
 * skriver rätt adress får aldrig hit ett enda byte, för skriptet laddas i ett
 * block som bara renderas vid just det felet.
 *
 * Canvas och inte SVG: kroppen ritas segment för segment med avtagande bredd,
 * och en SVG-path kan inte variera sin strokebredd längs vägen.
 *
 * Ritar över HELA fönstret, i ett lager som inte tar emot klick. Pekaren läses
 * därför från window och inte från canvasen, som aldrig får någon händelse.
 *
 * prefers-reduced-motion fryser ormen i en vågform i stället för att ta bort
 * den. En reducerad rörelse ska ge en stillsam orm, inte en tom ruta.
 */
(function () {
  const canvas = document.getElementById('orm-canvas');
  if (!canvas) return;

  const reducedQuery = matchMedia('(prefers-reduced-motion: reduce)');
  const green = '#2f7355';
  const dark = '#14432c';
  let target = { x: 0, y: 0, active: false };

  function setupCanvas(el) {
    const rect = el.getBoundingClientRect();
    const skala = window.devicePixelRatio || 1;
    el.width = Math.round(rect.width * skala);
    el.height = Math.round(rect.height * skala);
    const context = el.getContext('2d');
    context.setTransform(skala, 0, 0, skala, 0, 0);
    return { context, width: rect.width, height: rect.height };
  }

  // Antalet segment styr längden. 28 x 10 px ger en orm som hinner slingra
  // sig innan svansen tar slut.
  // Fler och längre segment än i en liten ruta: över en hel skärm ser 28 x 10
  // px ut som en daggmask. Steget skalas efter fönstret så ormen känns lika
  // stor på mobil som på desktop.
  const SEGMENT = 42;
  const STEG = Math.max(11, Math.min(22, window.innerWidth / 62));
  let points = Array.from({ length: SEGMENT }, (_, index) => ({ x: 80 - index * 8, y: 125 }));
  let lastPointerMove = 0;

  // Slumpvandring för läget när pekaren är borta. En cosinusbana är
  // förutsägbar efter tre varv - ormen ska kännas levande, inte som en
  // maskin. Riktningen driver med små slumpsteg och studsar mot kanterna.
  const wander = { x: 0, y: 0, vinkel: Math.random() * Math.PI * 2, startad: false };

  function slumpmal(width, height) {
    if (!wander.startad) {
      wander.x = width / 2;
      wander.y = height / 2;
      wander.startad = true;
    }
    // Liten slumpmässig kursändring per bildruta. Talet styr hur krokig
    // banan blir: större värde ger nervösare orm.
    wander.vinkel += (Math.random() - .5) * .12;
    const fart = 2.4;
    wander.x += Math.cos(wander.vinkel) * fart;
    wander.y += Math.sin(wander.vinkel) * fart;
    // Studsa innanför kanten i stället för att fastna i den.
    const marginal = 34;
    if (wander.x < marginal || wander.x > width - marginal) {
      wander.vinkel = Math.PI - wander.vinkel;
      wander.x = Math.min(Math.max(wander.x, marginal), width - marginal);
    }
    if (wander.y < marginal || wander.y > height - marginal) {
      wander.vinkel = -wander.vinkel;
      wander.y = Math.min(Math.max(wander.y, marginal), height - marginal);
    }
    return { x: wander.x, y: wander.y };
  }

  // Lyssna på FÖNSTRET. Overlayen har pointer-events:none och får därför
  // aldrig en egen pointermove - hade vi lyssnat på den vore ormen död.
  // Koordinaterna är redan viewport-relativa, som canvasen.
  window.addEventListener('pointermove', event => {
    if (event.pointerType === 'touch') return;
    target = { x: event.clientX, y: event.clientY, active: true };
    lastPointerMove = performance.now();
  }, { passive: true });
  document.addEventListener('pointerleave', () => { target.active = false; });

  // Ett fönsterbyte ändrar canvasens storlek. Utan det här ritas ormen i en
  // gammal upplösning och blir suddig eller hamnar utanför.
  window.addEventListener('resize', () => { wander.startad = false; }, { passive: true });

  // Huvudet från variant 5, ritat på canvas i stället för som SVG: ellips,
  // öga med pupill och kluven tunga. Det roteras efter färdriktningen, så
  // tungan pekar dit ormen är på väg.
  function ritaHuvud(ctx, head, nack) {
    const riktning = Math.atan2(head.y - nack.y, head.x - nack.x);
    ctx.save();
    ctx.translate(head.x, head.y);
    ctx.rotate(riktning);

    // Måtten är variant 5:s, skalade till den här kroppens bredd. Där är
    // kroppen 24 och huvudet 27 x 21, alltså 2,25 respektive 1,75 gånger
    // kroppens radie. Ett huvud som bara är lika brett som kroppen läses
    // inte som ett huvud.
    const r = STEG * 1.7 / 2;  // kroppens radie vid nacken
    ctx.fillStyle = dark;
    ctx.beginPath();
    ctx.ellipse(0, 0, r * 2.25, r * 1.75, 0, 0, Math.PI * 2);
    ctx.fill();

    // Tungan sticker ut ur nosen och delar sig. Röd mot den mörka nosen,
    // annars syns den inte.
    ctx.strokeStyle = '#c0392b';
    ctx.lineWidth = r * .22;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(r * 2.1, r * .1);
    ctx.lineTo(r * 3.3, r * .2);
    ctx.moveTo(r * 3.3, r * .2); ctx.lineTo(r * 3.8, -r * .25);
    ctx.moveTo(r * 3.3, r * .2); ctx.lineTo(r * 3.8, r * .65);
    ctx.stroke();

    // Ögat sitter på huvudets ovansida sett i färdriktningen.
    ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(r * .67, -r * .6, r * .55, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = dark;
    ctx.beginPath(); ctx.arc(r * .83, -r * .6, r * .28, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  function drawPointer(now) {
    const { context: ctx, width, height } = setupCanvas(canvas);
    ctx.clearRect(0, 0, width, height);
    const canFollow = target.active && now - lastPointerMove < 2600;
    const goal = canFollow ? target : slumpmal(width, height);
    if (reducedQuery.matches) {
      points = Array.from({ length: SEGMENT }, (_, index) => ({ x: width * .72 - index * STEG, y: height / 2 + Math.sin(index * .55) * 16 }));
    } else {
      // Långsammare när ormen vandrar själv än när den jagar pekaren.
      const tröghet = canFollow ? .075 : .035;
      points[0].x += (goal.x - points[0].x) * tröghet;
      points[0].y += (goal.y - points[0].y) * tröghet;
      for (let index = 1; index < points.length; index++) {
        const dx = points[index - 1].x - points[index].x;
        const dy = points[index - 1].y - points[index].y;
        const distance = Math.hypot(dx, dy) || 1;
        points[index].x = points[index - 1].x - dx / distance * STEG;
        points[index].y = points[index - 1].y - dy / distance * STEG;
      }
    }
    // Ett enda stroke kan bara ha EN bredd, så kroppen ritas segment för
    // segment. Bredden avtar mot svansen, som på en riktig orm. Round-caps
    // gör att de överlappande segmenten läses som en obruten kropp.
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = green;
    const BRED = STEG * 1.7;   // vid nacken
    const SMAL = STEG * .32;   // vid svansspetsen
    // Det yttersta segmentet ritas INTE. Så tunt som det blir läses det
    // som ett löst streck efter ormen i stället för som en svansspets.
    const SIST = points.length - 2;
    for (let index = SIST; index > 0; index--) {
      // 0 vid svansen, 1 vid huvudet.
      const andel = 1 - index / SIST;
      // Kvadrerad avsmalning: kroppen håller sin tjocklek längre och
      // spetsar av på slutet i stället för att smalna linjärt hela vägen.
      ctx.lineWidth = SMAL + (BRED - SMAL) * Math.pow(andel, .55);
      ctx.beginPath();
      ctx.moveTo(points[index].x, points[index].y);
      ctx.lineTo(points[index - 1].x, points[index - 1].y);
      ctx.stroke();
    }
    ritaHuvud(ctx, points[0], points[1]);
  }

  function loop(now) {
    drawPointer(now);
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();
