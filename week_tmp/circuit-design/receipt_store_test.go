package draft

import (
	"bytes"
	"errors"
	"fmt"
	nativeed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	"math/big"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
)

// Internal synthetic storage-only token; not evidence of actual proof validation.
func storeFixture(id int64) verifiedModelReceipt {
	k, err := nativeed.GenerateKey(bytes.NewReader(bytes.Repeat([]byte{7}, 32)))
	if err != nil {
		panic(err)
	}
	return verifiedModelReceipt{PublicReceipt{Session: big.NewInt(7), RecordID: big.NewInt(id), Commitment: big.NewInt(id + 100), Key: k.PublicKey}, big.NewInt(id + 1000).String(), true}
}
func TestStoreDurableAndDuplicate(t *testing.T) {
	root := privateStoreTemp(t)
	s, err := OpenReceiptStore(root)
	if err != nil {
		t.Fatal(err)
	}
	v := storeFixture(1)
	if err = s.commit(v); err != nil {
		t.Fatal(err)
	}
	if err = s.commit(v); !errors.Is(err, ErrDuplicateReceipt) {
		t.Fatal("duplicate not rejected", err)
	}
	reissued := storeFixture(2)
	reissued.nullifier = v.nullifier
	if err = s.commit(reissued); !errors.Is(err, ErrDuplicateObservation) {
		t.Fatal("reissued source accepted", err)
	}
	again, err := OpenReceiptStore(root)
	if err != nil {
		t.Fatal(err)
	}
	if n, err := again.Count(); err != nil || n != 1 {
		t.Fatal(n, err)
	}
	if err = s.commit(verifiedModelReceipt{}); err == nil {
		t.Fatal("unverified token accepted")
	}
	if err = s.VerifyAndStore(nil, nil, nil, ModelContext{}, 0); err == nil {
		t.Fatal("nil proof accepted")
	}
	if n, _ := s.Count(); n != 1 {
		t.Fatal("invalid proof changed state")
	}
}
func TestStoreConcurrent(t *testing.T) {
	root := privateStoreTemp(t)
	var accepted atomic.Int32
	var unexpected atomic.Int32
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			s, err := OpenReceiptStore(root)
			if err == nil {
				err = s.commit(storeFixture(1))
			}
			if err == nil {
				accepted.Add(1)
			} else if !errors.Is(err, ErrDuplicateReceipt) {
				unexpected.Add(1)
			}
		}()
	}
	wg.Wait()
	if accepted.Load() != 1 || unexpected.Load() != 0 {
		t.Fatal("atomic admission failed", accepted.Load(), unexpected.Load())
	}
}
func TestStoreFailurePreservesLedger(t *testing.T) {
	s, err := OpenReceiptStore(privateStoreTemp(t))
	if err != nil {
		t.Fatal(err)
	}
	if err = s.commit(storeFixture(1)); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(filepath.Join(s.root, "ledger.json"))
	s.beforeRename = func() error { return errors.New("injected pre-rename failure") }
	if err = s.commit(storeFixture(2)); err == nil {
		t.Fatal("failed save reported success")
	}
	after, _ := os.ReadFile(filepath.Join(s.root, "ledger.json"))
	if !bytes.Equal(before, after) {
		t.Fatal("failed save changed ledger")
	}
	s.beforeRename = nil
	path := filepath.Join(s.root, "ledger.json")
	if err = os.WriteFile(path, []byte("corrupt"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Count(); err == nil {
		t.Fatal("corrupt ledger silently reset")
	}
	data, _ := os.ReadFile(path)
	if string(data) != "corrupt" {
		t.Fatal("corrupt ledger destroyed")
	}
}
func TestStorePermissionsAndSymlink(t *testing.T) {
	root := privateStoreTemp(t)
	if err := os.Chmod(root, 0755); err != nil {
		t.Fatal(err)
	}
	if _, err := OpenReceiptStore(root); err == nil {
		t.Fatal("public directory accepted")
	}
	os.Chmod(root, 0700)
	s, err := OpenReceiptStore(root)
	if err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(t.TempDir(), "target")
	os.WriteFile(target, []byte("preserve"), 0600)
	if err = os.Symlink(target, filepath.Join(root, "ledger.json")); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Count(); err == nil {
		t.Fatal("symlink ledger accepted")
	}
	data, _ := os.ReadFile(target)
	if string(data) != "preserve" {
		t.Fatal("target modified")
	}
}
func TestStoreProcessHelper(t *testing.T) {
	root := os.Getenv("DRAFT_STORE_HELPER")
	if root == "" {
		t.Skip("subprocess fixture")
	}
	s, err := OpenReceiptStore(root)
	if err != nil {
		os.Exit(9)
	}
	if os.Getenv("DRAFT_STORE_CRASH") == "1" {
		s.beforeRename = func() error { os.Exit(70); return nil }
		_ = s.commit(storeFixture(2))
		os.Exit(9)
	}
	err = s.commit(storeFixture(1))
	if err == nil {
		os.Exit(0)
	}
	if errors.Is(err, ErrDuplicateReceipt) {
		os.Exit(3)
	}
	os.Exit(9)
}
func TestStoreCrossProcessAndCrash(t *testing.T) {
	root := privateStoreTemp(t)
	commands := make([]*exec.Cmd, 4)
	for i := range commands {
		cmd := exec.Command(os.Args[0], "-test.run=^TestStoreProcessHelper$")
		cmd.Env = append(os.Environ(), "DRAFT_STORE_HELPER="+root)
		if err := cmd.Start(); err != nil {
			t.Fatal(err)
		}
		commands[i] = cmd
	}
	success := 0
	for _, cmd := range commands {
		err := cmd.Wait()
		if err == nil {
			success++
		} else {
			var e *exec.ExitError
			if !errors.As(err, &e) || e.ExitCode() != 3 {
				t.Fatal("child failure", err)
			}
		}
	}
	if success != 1 {
		t.Fatal("cross-process duplicate", success)
	}
	cmd := exec.Command(os.Args[0], "-test.run=^TestStoreProcessHelper$")
	cmd.Env = append(os.Environ(), "DRAFT_STORE_HELPER="+root, "DRAFT_STORE_CRASH=1")
	err := cmd.Run()
	var exited *exec.ExitError
	if !errors.As(err, &exited) || exited.ExitCode() != 70 {
		t.Fatal("crash injection did not execute", err)
	}
	s, err := OpenReceiptStore(root)
	if err != nil {
		t.Fatal(err)
	}
	if n, err := s.Count(); err != nil || n != 1 {
		t.Fatal("crash damaged committed data", n, err)
	}
	pending, _ := filepath.Glob(filepath.Join(root, ".pending-*"))
	if len(pending) != 1 {
		t.Fatal("incomplete state not preserved")
	}
	if err = s.commit(storeFixture(2)); err != nil {
		t.Fatal("resume failed", err)
	}
	if n, _ := s.Count(); n != 2 {
		t.Fatal(n)
	}
}

func privateStoreTemp(t *testing.T) string {
	t.Helper()
	p := t.TempDir()
	if err := os.Chmod(p, 0700); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestStoreReadOnlyCapacityAndVersion(t *testing.T) {
	s, err := OpenReceiptStore(privateStoreTemp(t))
	if err != nil {
		t.Fatal(err)
	}
	if err = s.commit(storeFixture(1)); err != nil {
		t.Fatal(err)
	}
	if os.Getuid() != 0 {
		if err = os.Chmod(s.root, 0500); err != nil {
			t.Fatal(err)
		}
		err = s.commit(storeFixture(2))
		os.Chmod(s.root, 0700)
		if err == nil {
			t.Fatal("read-only save reported success")
		}
		if n, _ := s.Count(); n != 1 {
			t.Fatal("read-only failure changed count")
		}
	}
	payload, err := s.load()
	if err != nil {
		t.Fatal(err)
	}
	payload.Version = 2
	if err = s.save(payload); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(filepath.Join(s.root, "ledger.json"))
	if _, err = s.Count(); err == nil {
		t.Fatal("unknown schema silently accepted")
	}
	after, _ := os.ReadFile(filepath.Join(s.root, "ledger.json"))
	if !bytes.Equal(before, after) {
		t.Fatal("unknown schema changed")
	}
	capped, err := OpenReceiptStore(privateStoreTemp(t))
	if err != nil {
		t.Fatal(err)
	}
	full := ledgerPayload{Version: 1, Entries: map[string]ledgerEntry{}}
	for i := 0; i < 10000; i++ {
		full.Entries[fmt.Sprintf("%064x", i)] = ledgerEntry{digestText("test-nullifier", fmt.Sprint(i)), digestText("test-statement", fmt.Sprint(i))}
	}
	if err = capped.save(full); err != nil {
		t.Fatal(err)
	}
	if err = capped.commit(storeFixture(1)); err == nil {
		t.Fatal("capacity overflow accepted")
	}
	if n, err := capped.Count(); err != nil || n != 10000 {
		t.Fatal(n, err)
	}
}
