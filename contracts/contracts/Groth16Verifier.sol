// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract Groth16Verifier {
    // Scalar field size
    uint256 constant r    = 21888242871839275222246405745257275088548364400416034343698204186575808495617;
    // Base field size
    uint256 constant q   = 21888242871839275222246405745257275088696311157297823662689037894645226208583;

    // Verification Key data
    uint256 constant alphax  = 17357045683355656798897701527195139786960233498877809619353275893221946379004;
    uint256 constant alphay  = 11000614436873118403086556822572729481296129488129424888010942830378739595198;
    uint256 constant betax1  = 19441315152147356866004922768987516977628883010022971293285016624284582141162;
    uint256 constant betax2  = 21592193537706335373814651685388528086511830739632705952311853896235831218925;
    uint256 constant betay1  = 15982737604579475600964927723131672690937026406890983339856753174928043185647;
    uint256 constant betay2  = 4812418710010494561119208328288445509469594475284038214814116835936390596969;
    uint256 constant gammax1 = 11559732032986387107991004021392285783925812861821192530917403151452391805634;
    uint256 constant gammax2 = 10857046999023057135944570762232829481370756359578518086990519993285655852781;
    uint256 constant gammay1 = 4082367875863433681332203403145435568316851327593401208105741076214120093531;
    uint256 constant gammay2 = 8495653923123431417604973247489272438418190587263600148770280649306958101930;
    uint256 constant deltax1 = 14952212141831198852523874739481793285330540870828244242259191823843028072394;
    uint256 constant deltax2 = 21593927653963429784857076067646823554243762546953398729301120097265426080797;
    uint256 constant deltay1 = 17612485371177773982812867880820033353409135398285174870867684361178361822344;
    uint256 constant deltay2 = 1750222512217724043075020832731144097030493712691550528701130252319791576015;

    
    uint256 constant IC0x = 8698980884003396167929549806637124556471233958189815451294785749295278028254;
    uint256 constant IC0y = 15108065676307999630561568398479141207509715578763907408219031982214945440272;
    
    uint256 constant IC1x = 13507429210853214603267768891687810912524358648719484733245222914460414423660;
    uint256 constant IC1y = 9889073663536714373589581424126294502426310763299894414922333187522482236366;
    
    uint256 constant IC2x = 17096011412466425119708759295709498212475466205756485840125388095296875595885;
    uint256 constant IC2y = 14611855574266470537677027096944867677978561243253949014242730580380892290730;
    
    uint256 constant IC3x = 899321205318777831282788945570537805286370398942640826459943959378718860491;
    uint256 constant IC3y = 3196133804456031531296497753375592017464040316529945844897103046075947666114;
    
    uint256 constant IC4x = 17920950415929493580547039836610753178216983640589859282053273199076719782851;
    uint256 constant IC4y = 5094382036229353165778865216601827720201964670837883870992761633523329269497;
    
    uint256 constant IC5x = 18200664910202248389204280157257441359748458169147251895452701938378040972920;
    uint256 constant IC5y = 12911309188365040280757549490471457651207410652266719805804100543402257815342;
    
    uint256 constant IC6x = 19882619899318210297597304815302046608408482109611569214684535649394240149867;
    uint256 constant IC6y = 9116081598067608282382095477933605179254150115811474051749439305407516139250;
    
    uint256 constant IC7x = 2873588297263806068437159289800292580285070435559401718732016684826420301588;
    uint256 constant IC7y = 15666832532811496259795525218091121279299401063223382937927932930952365906527;
    
    uint256 constant IC8x = 737705921953506149764160277727491364802721501418447440440890080019852648357;
    uint256 constant IC8y = 14080054324734729351617991516044460857397640685766203597922483752535878579758;
    
    uint256 constant IC9x = 21841269846266258158964843034024055541107999092507142305111998715492652539636;
    uint256 constant IC9y = 2621178075475519558362604216319876604629338059774220527611385822381495560153;
    
    uint256 constant IC10x = 12250066308262719864302670854465589556130856564836928906829997729198374274219;
    uint256 constant IC10y = 13501398564588617749332098646946944749950398652197906528714533900046688592287;
    
    uint256 constant IC11x = 14625891166298862211005948481349486417756353430303365023606122912437454891940;
    uint256 constant IC11y = 17715132710592199963144436772583817448160674380786521627969749557753641562852;
    
    uint256 constant IC12x = 16729777724393289739269520510018227732721350483994749328684580394831009705940;
    uint256 constant IC12y = 3931612575525010848814761087134593724722783665604548651011331949945069446844;
    
    uint256 constant IC13x = 11383920457226189704800712910821419412039726110125571046810369018731489052222;
    uint256 constant IC13y = 7164132638786440948831852273766221696931136781648675478576965333550048476546;
    
    uint256 constant IC14x = 2026387820276783650384134614506313222328343762965975566250354636443434523921;
    uint256 constant IC14y = 13417265598564937571690706359448419360841054838648324318188210942701760790201;
    
    uint256 constant IC15x = 11269419248765284023160606690907343624003334909784877540870907884879828789739;
    uint256 constant IC15y = 19899245386703590548327184126954932246291309069202133105850833953911142158421;
    
    uint256 constant IC16x = 13769992422090027488932143575060435006619635027400864117650800387638267184142;
    uint256 constant IC16y = 9269627823085103906533862187071061394467664503636842567018083985930547523187;
    
    uint256 constant IC17x = 5965351659035108755800403476354655141931863925328489909726041839916957274928;
    uint256 constant IC17y = 8898598690975984170959998736020299671345555920972160608291861457628199429039;
    
    uint256 constant IC18x = 4084244003124812122523051952899710403723330506618872026878857272812970650978;
    uint256 constant IC18y = 11944187228933186391952280893493601645633289531218921528585190698783021137701;
    
 
    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(uint[2] calldata _pA, uint[2][2] calldata _pB, uint[2] calldata _pC, uint[18] calldata _pubSignals) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }
            
            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x
                
                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))
                
                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))
                
                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))
                
                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))
                
                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))
                
                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))
                
                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))
                
                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))
                
                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))
                
                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))
                
                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))
                
                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))
                
                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))
                
                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))
                
                g1_mulAccC(_pVk, IC15x, IC15y, calldataload(add(pubSignals, 448)))
                
                g1_mulAccC(_pVk, IC16x, IC16y, calldataload(add(pubSignals, 480)))
                
                g1_mulAccC(_pVk, IC17x, IC17y, calldataload(add(pubSignals, 512)))
                
                g1_mulAccC(_pVk, IC18x, IC18y, calldataload(add(pubSignals, 544)))
                

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))


                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)


                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F
            
            checkField(calldataload(add(_pubSignals, 0)))
            
            checkField(calldataload(add(_pubSignals, 32)))
            
            checkField(calldataload(add(_pubSignals, 64)))
            
            checkField(calldataload(add(_pubSignals, 96)))
            
            checkField(calldataload(add(_pubSignals, 128)))
            
            checkField(calldataload(add(_pubSignals, 160)))
            
            checkField(calldataload(add(_pubSignals, 192)))
            
            checkField(calldataload(add(_pubSignals, 224)))
            
            checkField(calldataload(add(_pubSignals, 256)))
            
            checkField(calldataload(add(_pubSignals, 288)))
            
            checkField(calldataload(add(_pubSignals, 320)))
            
            checkField(calldataload(add(_pubSignals, 352)))
            
            checkField(calldataload(add(_pubSignals, 384)))
            
            checkField(calldataload(add(_pubSignals, 416)))
            
            checkField(calldataload(add(_pubSignals, 448)))
            
            checkField(calldataload(add(_pubSignals, 480)))
            
            checkField(calldataload(add(_pubSignals, 512)))
            
            checkField(calldataload(add(_pubSignals, 544)))
            

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
             return(0, 0x20)
         }
     }
 }
