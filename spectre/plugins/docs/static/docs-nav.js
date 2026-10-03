/* Navigation des pages de documentation. */

/* Docs pages only: highlights the nav link matching whichever <section id="..."> is currently in
   view, using IntersectionObserver rather than a scroll listener (cheaper, no manual throttling). */
function initDocsNav() {
  const nav = document.querySelector(".docs-nav");
  const sections = document.querySelectorAll(".docs-content section[id]");
  if (!nav || sections.length === 0) return;
  const links = new Map([...nav.querySelectorAll("a")].map((a) => [a.getAttribute("href").slice(1), a]));
  const setActive = (id) => {
    links.forEach((a) => a.classList.remove("active"));
    const link = links.get(id);
    if (link) link.classList.add("active");
  };
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter((e) => e.isIntersecting);
      if (visible.length > 0) setActive(visible[0].target.id);
    },
    { rootMargin: "-10% 0px -70% 0px" }
  );
  sections.forEach((section) => observer.observe(section));
  if (sections[0]) setActive(sections[0].id);
}

initDocsNav();
