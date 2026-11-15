package org.smri.ridobserver.core
import kotlin.test.*
class CaptureBudgetTest {
    @Test fun stopReasonHasRoomWhenNormalWritesAreFull() {
        val b=CaptureBudget(100,20)
        assertTrue(b.allows(79,1));assertFalse(b.allows(80,1))
        assertTrue(b.allows(80,20,ending=true));assertFalse(b.allows(80,21,ending=true))
    }
    @Test fun corruptSizesAndOverflowFailClosed() {
        val b=CaptureBudget()
        assertFalse(b.allows(-1,1));assertFalse(b.allows(0,-1))
        assertFalse(b.allows(Long.MAX_VALUE,Long.MAX_VALUE,true))
        assertFalse(b.allows(1,Long.MAX_VALUE));assertFalse(b.allows(b.maxBytes+1,0,true))
    }
    @Test fun invalidConfigurationCannotRemoveStopReserve() {
        assertFailsWith<IllegalArgumentException> {CaptureBudget(0,0)}
        assertFailsWith<IllegalArgumentException> {CaptureBudget(10,10)}
    }
}
