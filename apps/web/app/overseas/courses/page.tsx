import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import CollectionExplorer from "@/components/CollectionExplorer";
import {publicApi} from "@/lib/api";

export default async function Courses() {
  let courses: any[] = [];
  try { courses = await publicApi<any[]>("/api/v1/public/overseas-courses"); } catch {}
  const items = courses.map(course => ({
    id: String(course.id), searchText: `${course.title} ${course.university} ${course.country} ${course.category} ${course.level} ${course.duration} ${course.intake}`,
    filters: {category: course.category, level: course.level, country: course.country}, sortValues: {title: course.title, university: course.university, country: course.country},
    content: <div className="card"><span className="badge">{course.category}</span><h3 style={{marginTop: 12}}>{course.title}</h3><p><strong>{course.university}</strong><br/><span className="muted">{course.country}</span></p><p className="muted">{course.level} · {course.duration} · {course.intake}</p><strong>{course.tuition_fee}</strong></div>,
  }));
  return <PublicShell division="overseas"><PageHero eyebrow="Course Discovery" title="Overseas Courses" description="Explore seeded examples across Engineering, Business, Management, Healthcare, Hospitality, Computer Science, AI, Cyber Security, Data Science, MBA, Masters, Bachelors and Diploma pathways."/><section className="section"><div className="container"><CollectionExplorer items={items} noun="courses" searchPlaceholder="Search course, university, or intake…" filters={[{key: "category", label: "Category"}, {key: "level", label: "Level"}, {key: "country", label: "Country"}]} sorts={[{value: "title", key: "title", label: "Course A–Z"}, {value: "university", key: "university", label: "University A–Z"}, {value: "country", key: "country", label: "Country A–Z"}]} empty={<div className="card"><h3>No courses available</h3><p className="muted">Published overseas courses will appear here.</p></div>}/></div></section></PublicShell>;
}
