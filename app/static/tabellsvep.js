// Visa att en tabell fortsätter i sidled.
//
// Hämtat från slöjda.de (TASK-1039 där), där ansatsen redan prövats ut. Dess
// slutsats bär hit: en skugga BAKOM innehållet kan inte fungera, för celler
// med egen bakgrund målar över den precis där den behövs. Här är det
// .badge-pillarna i statuskolumnen som gör det.
//
// Innehållet tonas därför ut med en mask, och masken ligger på behållarens
// box i stället för på det som skrollar - då står toningen stilla i kanten
// medan innehållet glider förbi.
//
// Skriptet gör bara en sak: säger vilket håll det finns mer åt. Utseendet
// ligger i style.css. Utan skript sätts attributet aldrig, ingen mask läggs
// på, och tabellen fungerar som förut - skrollen har aldrig hängt på det här.

const MARGINAL = 2; // px. scrollLeft kan vara bråkdelar vid zoom.

function lage(svep) {
  const mer_vanster = svep.scrollLeft > MARGINAL;
  const mer_hoger =
    svep.scrollLeft + svep.clientWidth < svep.scrollWidth - MARGINAL;
  if (mer_vanster && mer_hoger) return "bada";
  if (mer_vanster) return "vanster";
  if (mer_hoger) return "hoger";
  return "";
}

function uppdatera(svep) {
  const nytt = lage(svep);
  if (nytt) svep.dataset.mer = nytt;
  else delete svep.dataset.mer;
}

for (const svep of document.querySelectorAll(".table-wrap")) {
  uppdatera(svep);
  svep.addEventListener("scroll", () => uppdatera(svep), { passive: true });
  // Bredden ändras av mer än fönstret: en utfälld QR-rad i tabellen, en
  // laddad bild, eller en kolumn som växer när text kommer in.
  // ResizeObserver täcker alla tre, medan ett fönsterlyssnande missat dem.
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(() => uppdatera(svep)).observe(svep);
  }
}
