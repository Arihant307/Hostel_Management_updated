import { useEffect } from 'react';
import Modal from '../../components/ui/Modal.jsx';
import Button from '../../components/ui/Button.jsx';
import Input, { Select } from '../../components/ui/Input.jsx';
import { FormError } from '../../components/ui/Misc.jsx';
import useForm from '../../hooks/useForm.js';
import { roomService } from '../../services/resources.js';
import { fromMinor, toMinor } from '../../utils/format.js';

const EMPTY = { block: '', room_number: '', floor: '0', room_type: 'double', capacity: '2', monthly_fee: '', amenities: '' };
const DEFAULT_CAPACITY = { single: 1, double: 2, triple: 3, dormitory: 6 };

export default function RoomFormModal({ open, room, onClose, onSaved }) {
  const isEdit = Boolean(room);
  const form = useForm(EMPTY);

  useEffect(() => {
    if (!open) return;
    form.reset(room ? {
      block: room.block, room_number: room.room_number, floor: String(room.floor),
      room_type: room.room_type, capacity: String(room.capacity),
      monthly_fee: fromMinor(room.monthly_fee_minor), amenities: room.amenities ?? '',
    } : EMPTY);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, room]);

  const typeBinding = form.bind('room_type');
  const onTypeChange = (e) => {
    typeBinding.onChange(e);
    if (!isEdit) form.setValues((v) => ({ ...v, capacity: String(DEFAULT_CAPACITY[e.target.value]) }));
  };

  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit(
      (v) => {
        const payload = {
          block: v.block.trim(), room_number: v.room_number.trim(), floor: Number(v.floor),
          room_type: v.room_type, capacity: Number(v.capacity),
          monthly_fee_minor: toMinor(v.monthly_fee), amenities: v.amenities.trim() || null,
        };
        return isEdit ? roomService.update(room.id, payload) : roomService.create(payload);
      },
      {
        validate: (v) => ({
          block: !v.block.trim() && 'Enter the block.',
          room_number: !v.room_number.trim() && 'Enter the room number.',
          floor: !/^-?\d+$/.test(v.floor) && 'Enter a whole number.',
          capacity: !(Number(v.capacity) >= 1 && Number(v.capacity) <= 20) && 'Between 1 and 20 beds.',
          monthly_fee: Number.isNaN(toMinor(v.monthly_fee)) && 'Enter an amount like 4500 or 4500.50.',
        }),
      },
    );
    if (result) onSaved(result);
  };

  // The API reports the fee as monthly_fee_minor; show it on the visible field.
  const feeError = form.errors.monthly_fee || form.errors.monthly_fee_minor;

  return (
    <Modal
      open={open}
      onClose={form.submitting ? undefined : onClose}
      title={isEdit ? `Edit room ${room.block}-${room.room_number}` : 'Add room'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
          <Button type="submit" form="room-form" loading={form.submitting}>{isEdit ? 'Save changes' : 'Add room'}</Button>
        </>
      }
    >
      <form id="room-form" onSubmit={save} className="space-y-4" noValidate>
        <FormError message={form.formError} />
        <div className="grid gap-4 sm:grid-cols-3">
          <Input label="Block" required {...form.bind('block')} placeholder="A" />
          <Input label="Room number" required {...form.bind('room_number')} placeholder="101" />
          <Input label="Floor" type="number" required {...form.bind('floor')} />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Select label="Room type" required {...typeBinding} onChange={onTypeChange}>
            <option value="single">Single</option>
            <option value="double">Double</option>
            <option value="triple">Triple</option>
            <option value="dormitory">Dormitory</option>
          </Select>
          <Input label="Bed capacity" type="number" min="1" max="20" required {...form.bind('capacity')}
            hint={isEdit ? `Currently ${room.occupied_beds} occupied` : undefined} />
          <Input label="Monthly fee (₹)" inputMode="decimal" required {...form.bind('monthly_fee')} error={feeError} />
        </div>
        <Input label="Amenities" {...form.bind('amenities')} placeholder="Attached bath, Wi-Fi, study table" />
      </form>
    </Modal>
  );
}
