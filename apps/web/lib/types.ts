export type Program = { id:string; slug:string; category:string; title:string; summary:string; duration:string; eligibility:string; fees:number; certification:string; curriculum:string[]; placement_assistance:string; trainer_name:string };
export type Country = { id:string; slug:string; name:string; overview:string; tuition:string; living_expenses:string; visa_process:string[]; work_opportunities:string; post_study_work:string; pr_opportunities:string; faq:{question:string;answer:string}[] };
export type University = { id:string; country_id:string; slug:string; name:string; city:string; overview:string; eligibility:string; requirements:string[]; deadlines:string[]; scholarships:string[] };
export type PortalPayload = {
  title:string; subtitle:string; metrics:{label:string;value:string|number}[];
  actions:{label:string;href:string}[]; columns:{key:string;label:string;type?:string}[];
  rows:Record<string, unknown>[]; panels:{title:string;items:string[]}[];
};
export type User = {id:string; email:string; full_name:string; role:string; division:string; phone?:string; profile:Record<string,unknown>};
export type CareerPath = {id:string; division:string; slug:string; title:string; summary:string; skills:string[]; related_program_slugs:string[]; outcomes:string};
export type RealProject = {id:string; division:string; slug:string; title:string; summary:string; description:string; tech_stack:string[]};
export type Testimonial = {id:string; division:string; person_name:string; headline:string; quote:string; rating:number};
export type ContentPage = {id:string; slug:string; title:string; body:string; seo:Record<string,unknown>};
export type AvailableBatch = {id:string; name:string; program_id:string; program:string; schedule:string; timezone:string; capacity:number; available:number; start_date:string; end_date:string; mode:string};
export type LiveSessionInfo = {id:string; batch:string; title:string; starts_at:string; ends_at:string; provider:string; meeting_url:string|null; host_url:string|null; recording_url:string|null; recording_status:string; sync_status:string; status:string};
export type Webinar = {id:string; division:string; title:string; event_type:string; starts_at:string; location:string; description:string; is_past:boolean; registration_url?:string|null};
export type Scholarship = {id:string; title:string; eligibility:string; amount:string; deadline:string|null};
