package draft

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
	"syscall"

	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
)

var ErrDuplicateReceipt = errors.New("receipt already stored")
var ErrDuplicateObservation = errors.New("same declared observation already stored")

type ledgerEntry struct {
	Nullifier string `json:"nullifier_sha256"`
	Statement string `json:"statement_sha256"`
}
type ledgerPayload struct {
	Version int                    `json:"version"`
	Entries map[string]ledgerEntry `json:"entries"`
}
type ledgerDisk struct {
	Payload  ledgerPayload `json:"payload"`
	Checksum string        `json:"checksum"`
}

// ReceiptStore is a local Unix file-lock/atomic-rename store, not a database of
// positions. Both receipt ID and declared-source nullifier are unique.
type ReceiptStore struct {
	root         string
	mu           sync.Mutex
	beforeRename func() error
}

func ownerPrivate(info os.FileInfo) bool {
	stat, ok := info.Sys().(*syscall.Stat_t)
	return ok && stat.Uid == uint32(os.Getuid()) && info.Mode().Perm()&0077 == 0
}
func OpenReceiptStore(root string) (*ReceiptStore, error) {
	abs, err := filepath.Abs(root)
	if err != nil {
		return nil, err
	}
	if err = os.MkdirAll(abs, 0700); err != nil {
		return nil, err
	}
	info, err := os.Lstat(abs)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 || !ownerPrivate(info) {
		return nil, fmt.Errorf("owner-private nonsymlink store directory required")
	}
	abs, err = filepath.EvalSymlinks(abs)
	if err != nil {
		return nil, err
	}
	return &ReceiptStore{root: abs}, nil
}
func privateFile(path string, flags int) (*os.File, error) {
	fd, err := syscall.Open(path, flags|syscall.O_NOFOLLOW, 0600)
	if err != nil {
		return nil, err
	}
	f := os.NewFile(uintptr(fd), path)
	info, err := f.Stat()
	if err != nil || !info.Mode().IsRegular() || !ownerPrivate(info) {
		f.Close()
		return nil, fmt.Errorf("owner-private regular file required")
	}
	return f, nil
}
func (s *ReceiptStore) lock() (func(), error) {
	s.mu.Lock()
	f, err := privateFile(filepath.Join(s.root, ".lock"), syscall.O_RDWR|syscall.O_CREAT)
	if err != nil {
		s.mu.Unlock()
		return nil, err
	}
	if err = syscall.Flock(int(f.Fd()), syscall.LOCK_EX); err != nil {
		f.Close()
		s.mu.Unlock()
		return nil, err
	}
	return func() { syscall.Flock(int(f.Fd()), syscall.LOCK_UN); f.Close(); s.mu.Unlock() }, nil
}
func checksum(p ledgerPayload) string {
	b, _ := json.Marshal(p)
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
func (s *ReceiptStore) load() (ledgerPayload, error) {
	empty := ledgerPayload{Version: 1, Entries: map[string]ledgerEntry{}}
	f, err := privateFile(filepath.Join(s.root, "ledger.json"), syscall.O_RDONLY)
	if os.IsNotExist(err) {
		return empty, nil
	}
	if err != nil {
		return empty, err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil || info.Size() > 4<<20 {
		return empty, fmt.Errorf("ledger size invalid")
	}
	data, err := io.ReadAll(io.LimitReader(f, 4<<20+1))
	if err != nil {
		return empty, err
	}
	var disk ledgerDisk
	if err = json.Unmarshal(data, &disk); err != nil {
		return empty, fmt.Errorf("ledger corrupt; preserved")
	}
	if disk.Payload.Version != 1 || disk.Payload.Entries == nil || len(disk.Payload.Entries) > 10000 || disk.Checksum != checksum(disk.Payload) {
		return empty, fmt.Errorf("ledger format/checksum invalid; preserved")
	}
	for k, v := range disk.Payload.Entries {
		for _, x := range []string{k, v.Nullifier, v.Statement} {
			b, err := hex.DecodeString(x)
			if err != nil || len(b) != 32 {
				return empty, fmt.Errorf("ledger record invalid; preserved")
			}
		}
	}
	return disk.Payload, nil
}
func (s *ReceiptStore) save(p ledgerPayload) error {
	random := make([]byte, 12)
	if _, err := io.ReadFull(rand.Reader, random); err != nil {
		return err
	}
	temp := filepath.Join(s.root, ".pending-"+hex.EncodeToString(random))
	f, err := privateFile(temp, syscall.O_WRONLY|syscall.O_CREAT|syscall.O_EXCL)
	if err != nil {
		return err
	}
	defer os.Remove(temp)
	b, err := json.Marshal(ledgerDisk{p, checksum(p)})
	if err == nil {
		_, err = f.Write(append(b, '\n'))
	}
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	if s.beforeRename != nil {
		if err = s.beforeRename(); err != nil {
			return err
		}
	}
	if err = os.Rename(temp, filepath.Join(s.root, "ledger.json")); err != nil {
		return err
	}
	dir, err := os.Open(s.root)
	if err != nil {
		return fmt.Errorf("commit durability uncertain: %w", err)
	}
	defer dir.Close()
	if err = dir.Sync(); err != nil {
		return fmt.Errorf("commit durability uncertain: %w", err)
	}
	return nil
}
func digestText(domain, text string) string {
	h := sha256.Sum256([]byte(domain + "\x00" + text))
	return hex.EncodeToString(h[:])
}
func (s *ReceiptStore) commit(v verifiedModelReceipt) error {
	if !v.verified || v.receipt.Session == nil || v.receipt.RecordID == nil || v.receipt.Commitment == nil || v.nullifier == "" {
		return fmt.Errorf("verified receipt token required")
	}
	unlock, err := s.lock()
	if err != nil {
		return err
	}
	defer unlock()
	p, err := s.load()
	if err != nil {
		return err
	}
	key := digestText("receipt-v1", ReceiptReplayKey(v.receipt))
	n := digestText("observation-v1", v.nullifier)
	if _, ok := p.Entries[key]; ok {
		return ErrDuplicateReceipt
	}
	for _, old := range p.Entries {
		if old.Nullifier == n {
			return ErrDuplicateObservation
		}
	}
	if len(p.Entries) >= 10000 {
		return fmt.Errorf("ledger capacity reached")
	}
	p.Entries[key] = ledgerEntry{n, digestText("statement-v1", v.receipt.Commitment.String())}
	return s.save(p)
}

// VerifyAndStore cannot persist a caller-supplied unverified receipt. Verify is
// outside the file lock; unique checks repeat atomically under lock after it.
func (s *ReceiptStore) VerifyAndStore(proof groth16.Proof, vk groth16.VerifyingKey, public witness.Witness, e ModelContext, now uint64) error {
	v, err := VerifyModelProof(proof, vk, public, e, now)
	if err != nil {
		return err
	}
	return s.commit(v)
}
func (s *ReceiptStore) Count() (int, error) {
	unlock, err := s.lock()
	if err != nil {
		return 0, err
	}
	defer unlock()
	p, err := s.load()
	return len(p.Entries), err
}
