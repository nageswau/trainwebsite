"use client";

import { useState } from "react";

import IntakePicker from "@/components/IntakePicker";

// ccrm-053 (PF2): ccrm-047's month + year picker inside a plain GET filter form -- the chosen "Sep 2027" travels as `name`.
export default function IntakeFilter({ id, name, defaultValue }: { id: string; name: string; defaultValue: string }) {
  const [value, setValue] = useState(defaultValue);
  return (
    <>
      <IntakePicker id={id} label="Intake" value={value} onChange={setValue} />
      <input type="hidden" name={name} value={value} />
    </>
  );
}
