// =============================
// Premium Motion Pack — JS
// =============================
(function(){
// Enable page entrance once styles are ready
window.addEventListener('load', () => document.body.classList.add('motion-ready'));


// Intersection Observer for reveal-on-scroll
const io = new IntersectionObserver((entries) => {
entries.forEach(e => {
if (e.isIntersecting){
e.target.classList.add('in');
if (!e.target.dataset.once) return; // allow multiple if not once
io.unobserve(e.target);
}
});
}, { threshold: 0.14 });


document.querySelectorAll('.a-fade, .a-up, .a-down, .a-left, .a-right, .stagger > *, .chart-reveal').forEach(el => io.observe(el));


// Stagger helper for lists/grids
document.querySelectorAll('.stagger').forEach(group => {
const children = [...group.children];
children.forEach((child, i) => child.style.transitionDelay = `${Math.min(i*40, 360)}ms`);
});


// Toast helper
window.showToast = function(el){
el.classList.remove('hide');
el.classList.add('toast');
setTimeout(() => el.classList.add('hide'), 2400);
}


// Gentle parallax on cards
const tilt = (e) => {
const el = e.currentTarget;
const r = el.getBoundingClientRect();
const x = (e.clientX - r.left) / r.width - 0.5;
const y = (e.clientY - r.top) / r.height - 0.5;
el.style.transform = `translateY(-3px) rotateX(${y*-2}deg) rotateY(${x*2}deg)`;
};
const untilt = (e) => { e.currentTarget.style.transform = ''; };
document.querySelectorAll('.card[data-tilt]').forEach(c => { c.addEventListener('mousemove', tilt); c.addEventListener('mouseleave', untilt); });


// Chart.js entry animation enhancer (if Chart is present)
if (window.Chart){
Chart.defaults.animation.duration = 700;
Chart.defaults.animation.easing = 'easeOutQuart';
// Reveal container when chart finishes
Chart.defaults.plugins.animationStart = {
id: 'revealOnComplete',
afterRender(chart, args, opts){
const wrap = chart.canvas.closest('.chart-reveal');
if (wrap) wrap.classList.add('in');
}
};
}
})();