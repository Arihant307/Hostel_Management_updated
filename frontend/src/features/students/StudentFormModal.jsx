import { useEffect } from 'react';
import Modal from '../../components/ui/Modal.jsx';
import Button from '../../components/ui/Button.jsx';
import Input, { Select } from '../../components/ui/Input.jsx';
import { FormError } from '../../components/ui/Misc.jsx';
import useForm from '../../hooks/useForm.js';
import { studentService } from '../../services/resources.js';
import { PASSWORD_RULES, isStrongPassword } from '../../utils/password.js';
import { todayISO } from '../../utils/format.js';

const EMPTY = {
  full_name: '', email: '', phone: '', student_code: '', course: '', department: '',
  academic_year: '1', gender: '', date_of_birth: '', address: '', emergency_contact_name: '',
  emergency_contact_phone: '', emergency_contact_relation: '', registration_date: todayISO(), password: '',
};

function fromStudent(s) {
  return {
    ...EMPTY,
    full_name: s.full_name, email: s.email, phone: s.phone ?? '', student_code: s.student_code,
    course: s.course, department: s.department, academic_year: String(s.academic_year),
    gender: s.gender ?? '', date_of_birth: s.date_of_birth ?? '', address: s.address ?? '',
    emergency_contact_name: s.emergency_contact.name, emergency_contact_phone: s.emergency_contact.phone,
    emergency_contact_relation: s.emergency_contact.relation ?? '', registration_date: s.registration_date,
  };
}

function validate(v, isEdit) {
  return {
    full_name: v.full_name.trim().length < 2 && 'Enter the full name.',
    email: !/^\S+@\S+\.\S+$/.test(v.email.trim()) && 'Enter a valid email.',
    student_code: v.student_code.trim().length < 2 && 'Enter the student ID.',
    course: !v.course.trim() && 'Enter the course.',
    department: !v.department.trim() && 'Enter the department.',
    emergency_contact_name: v.emergency_contact_name.trim().length < 2 && 'Enter a contact name.',
    emergency_contact_phone: !/^\+?[0-9][0-9\s-]{6,18}[0-9]$/.test(v.emergency_contact_phone.trim()) && 'Enter a valid phone number.',
    phone: v.phone.trim() && !/^\+?[0-9][0-9\s-]{6,18}[0-9]$/.test(v.phone.trim()) && 'Enter a valid phone number.',
    password: !isEdit && !isStrongPassword(v.password) && 'Password does not meet the requirements.',
  };
}

export default function StudentFormModal({ open, student, onClose, onSaved }) {
  const isEdit = Boolean(student);
  const form = useForm(EMPTY);

  useEffect(() => {
    if (open) form.reset(student ? fromStudent(student) : EMPTY);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, student]);

  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit(
      (v) => {
        const payload = {
          ...v,
          academic_year: Number(v.academic_year),
          phone: v.phone.trim() || null,
          gender: v.gender || null,
          date_of_birth: v.date_of_birth || null,
          address: v.address.trim() || null,
          emergency_contact_relation: v.emergency_contact_relation.trim() || null,
        };
        if (isEdit) {
          delete payload.password;
          return studentService.update(student.id, payload);
        }
        return studentService.create(payload);
      },
      { validate: (v) => validate(v, isEdit) },
    );
    if (result) onSaved(result);
  };

  return (
    <Modal
      open={open}
      onClose={form.submitting ? undefined : onClose}
      title={isEdit ? 'Edit student' : 'Register student'}
      description={isEdit ? undefined : 'Creates the student record and their sign-in account.'}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
          <Button type="submit" form="student-form" loading={form.submitting}>
            {isEdit ? 'Save changes' : 'Register student'}
          </Button>
        </>
      }
    >
      <form id="student-form" onSubmit={save} className="space-y-5" noValidate>
        <FormError message={form.formError} />
        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Personal details</legend>
          <Input label="Full name" required {...form.bind('full_name')} />
          <Input label="Student ID" required {...form.bind('student_code')} placeholder="e.g. CS2026-014" />
          <Input label="Email" type="email" required {...form.bind('email')} autoComplete="off" />
          <Input label="Phone" type="tel" {...form.bind('phone')} />
          <Select label="Gender" {...form.bind('gender')}>
            <option value="">Prefer not to say</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="other">Other</option>
          </Select>
          <Input label="Date of birth" type="date" {...form.bind('date_of_birth')} max={todayISO()} />
          <div className="sm:col-span-2">
            <Input label="Address" {...form.bind('address')} />
          </div>
        </fieldset>
        <fieldset className="grid gap-4 sm:grid-cols-3">
          <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Academic</legend>
          <Input label="Course" required {...form.bind('course')} placeholder="B.Tech" />
          <Input label="Department" required {...form.bind('department')} placeholder="Computer Science" />
          <Select label="Academic year" required {...form.bind('academic_year')}>
            {[1, 2, 3, 4, 5, 6].map((y) => <option key={y} value={y}>Year {y}</option>)}
          </Select>
          <Input label="Registration date" type="date" required {...form.bind('registration_date')} max={todayISO()} />
        </fieldset>
        <fieldset className="grid gap-4 sm:grid-cols-3">
          <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Emergency contact</legend>
          <Input label="Name" required {...form.bind('emergency_contact_name')} />
          <Input label="Phone" type="tel" required {...form.bind('emergency_contact_phone')} />
          <Input label="Relation" {...form.bind('emergency_contact_relation')} placeholder="Parent" />
        </fieldset>
        {!isEdit && (
          <fieldset>
            <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Sign-in</legend>
            <Input
              label="Temporary password"
              type="password"
              required
              autoComplete="new-password"
              {...form.bind('password')}
              hint={PASSWORD_RULES.map((r) => r.label).join(' · ')}
            />
          </fieldset>
        )}
      </form>
    </Modal>
  );
}
